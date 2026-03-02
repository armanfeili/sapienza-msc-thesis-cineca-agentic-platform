from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse

from db.redis_cache.client import get_redis
from src.schemas.jobs import JobCreateRequest as JobRequest, JobEventResponse, JobListResponse, JobResponse
from src.config import settings
from src.provenance import record_provenance
from src.security.jwt import get_current_principal
from src.security.perm import current_permissions
from src.utils.pagination import compute_etag
from src.utils.principal import principal_identity

# Initialize logger
logger = logging.getLogger(__name__)

# PostgreSQL backend support (feature flag: USE_POSTGRES_JOBS)
try:
    from sqlalchemy.orm import Session

    from db.postgres_control.database import get_db
    from src.services.jobs_service import JobsService

    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False

router = APIRouter(tags=["jobs"])

# Import new store infrastructure for POST /jobs POC
import contextlib

from src.jobs.factory import get_stores
from src.jobs.memory_store import create_idempotency_key
from src.jobs.models import JobDocument, JobStatus, SSEEvent
from src.services import job_store

# Backwards compatibility aliases (remove later if unused elsewhere)
_JOBS = job_store.jobs
_JOB_EXPIRY = job_store.job_expiry
_EVENT_BUFFER = job_store.event_buffer
_EVENT_BUFFER_MAX = job_store.EVENT_BUFFER_MAX


def _use_postgres_backend() -> bool:
    """Check if PostgreSQL backend should be used for jobs."""
    return POSTGRES_AVAILABLE and getattr(settings, "USE_POSTGRES_JOBS", False)


def _run_async(coro):
    """Helper to run async operations in sync context (for worker threads).

    IMPORTANT: This is ONLY safe to use in background worker threads spawned
    by threading.Thread, NOT in FastAPI request handlers which already run
    in an async event loop. Request handlers should use 'await' directly.
    """
    return asyncio.run(coro)


def _start_cleanup_thread():
    try:
        retention_days = int(getattr(settings, "JOB_RETENTION_DAYS", 7))
    except Exception:
        retention_days = 7
    job_store.start_retention_cleaner(retention_days=retention_days)


def _validate_job_id_uuid(job_id: str) -> None:
    """Validate job_id is a valid UUID, raise 400 if not."""
    try:
        uuid.UUID(job_id)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid job_id format: expected UUID, got '{job_id}'",
            headers={"X-Request-Id": job_id},
        )


@router.get(
    "",
    name="list_user_jobs",
    response_model=JobListResponse,
    summary="List caller's jobs (user-scoped)",
    description=(
        "GET /v1/jobs – List your background jobs\n\n"
        "**Why we need this endpoint:**\n"
        "- **Progress monitoring**: Users need to see which of their long-running operations are still processing vs. complete.\n"
        "- **Error discovery**: Shows which jobs failed so users can investigate and retry.\n"
        "- **Job management**: Users can find job IDs to cancel unwanted operations or retrieve results.\n"
        "- **Dashboard building**: Front-end apps display job lists to give users visibility into background work.\n"
        "- Without this endpoint, users wouldn't know if their requests succeeded, failed, or are still running.\n\n"
        "**What it does:**\n"
        "- Returns all jobs you created, with optional filtering by status\n"
        "- Supports pagination for large result sets\n"
        "- Includes caching to reduce server load when polling\n\n"
        "**Access:**\n"
        "- Any authenticated user (shows only your own jobs)\n"
        "- Admin users should use `/admin/jobs` to see all users' jobs\n\n"
        "**Behavior:**\n"
        "- **Filtering**: Add `?status=running` or `?status=queued&status=running` to filter results\n"
        "- **Pagination**: Results are sorted newest first (default 25 per page, max 50). Use `next_page_token` from response to get more\n"
        "- **Caching**: Returns `ETag` header. Send it back as `If-None-Match` to get `304 Not Modified` when nothing changed\n"
        "- **Privacy**: You only see your own jobs (filtered by token owner). Other users' jobs return empty list\n\n"
        "**Responses:**\n"
        "- 200: OK – Job list with pagination info (`items`, `total`, `has_more`, `next_page_token`)\n"
        "- 304: Not Modified – No changes since your last request (when using If-None-Match)\n"
        "- 400: Bad Request – Invalid page_token (must be numeric offset like '0', '25')\n"
        "- 401: Unauthorized – Missing or invalid authentication token\n\n"
        "**Examples:**\n"
        "```bash\n"
        "# List all your jobs\n"
        "curl -X GET http://localhost:8000/v1/jobs \\\n"
        '     -H "Authorization: Bearer $TOKEN"\n\n'
        "# Filter by status\n"
        'curl -X GET "http://localhost:8000/v1/jobs?status=running&status=queued" \\\n'
        '     -H "Authorization: Bearer $TOKEN"\n\n'
        "# Efficient polling with ETag (returns 304 if unchanged)\n"
        "curl -X GET http://localhost:8000/v1/jobs \\\n"
        '     -H "Authorization: Bearer $TOKEN" \\\n'
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
    },
)
async def list_user_jobs(
    request: Request,
    response: Response,
    user=Depends(get_current_principal),
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
    db: Session = Depends(get_db) if POSTGRES_AVAILABLE else None,
) -> Response:
    """List jobs owned by the authenticated user with optional filters and pagination."""

    # Route to PostgreSQL backend if enabled
    if _use_postgres_backend() and db is not None:
        return await _list_jobs_postgres(
            request=request,
            response=response,
            user=user,
            db=db,
            status_filter=status_filter,
            limit=limit,
            page_token=page_token,
        )

    # Legacy implementation (memory/Redis store)
    # Get caller identity
    owner_sub = principal_identity(user)
    tenant = getattr(getattr(request, "state", None), "tenant_id", None) or "global"

    # Get store implementation
    job_store_impl, _, _ = get_stores()

    # Parse status filter
    status_enum = None
    if status_filter:
        # If multiple statuses, we'll need to query each and merge (memory mode handles this)
        # For Redis mode with single status, use the status filter
        if len(status_filter) == 1:
            try:
                status_enum = JobStatus(status_filter[0])
            except ValueError:
                status_enum = None

    # Pagination with validation
    start_idx = 0
    if page_token:
        try:
            start_idx = int(page_token)
            if start_idx < 0:
                raise HTTPException(status_code=400, detail="Invalid page_token: offset must be non-negative")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid page_token: must be a valid offset integer")

    # List jobs by owner with optional status filter
    job_docs, total = await job_store_impl.list_by_owner(
        owner=owner_sub, status=status_enum, offset=start_idx, limit=limit
    )

    # If multiple status filters, filter in-memory (for simplicity)
    if status_filter and len(status_filter) > 1:
        job_docs = [j for j in job_docs if j.status.value in status_filter]
        total = len(job_docs)  # Approximate total (not exact for pagination)

    # Validate page_token bounds
    if page_token and start_idx >= total and total > 0:
        raise HTTPException(status_code=400, detail=f"Invalid page_token: offset {start_idx} exceeds total {total}")

    end_idx = start_idx + len(job_docs)
    has_more = end_idx < total
    next_token = str(end_idx) if has_more else None

    # Build response items
    items = []
    for job in job_docs:
        items.append(
            JobResponse(
                id=job.id,
                type=job.type,
                status=job.status.value,
                created_at=job.created_at.isoformat() + "Z"
                if not job.created_at.isoformat().endswith("Z")
                else job.created_at.isoformat(),
                updated_at=job.updated_at.isoformat() + "Z"
                if job.updated_at and not job.updated_at.isoformat().endswith("Z")
                else (job.updated_at.isoformat() if job.updated_at else None),
                tenant_id=job.tenant_id,
                owner=job.owner,
                result=job.result,
            )
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
        "route": "user_jobs",
        "owner": owner_sub,
        "tenant": tenant,
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
            # X-Request-Id is set by middleware
        },
    )


@router.get(
    "/{job_id}",
    name="get_job",
    response_model=JobResponse,
    summary="Get job status (supports conditional caching)",
    description=(
        "GET /v1/jobs/{job_id} – Check a specific job's status and result\n\n"
        "**Why we need this endpoint:**\n"
        "- **Progress checking**: After creating a job, users need to check if it completed, failed, or is still running.\n"
        "- **Result retrieval**: Final output data is only available through this endpoint after job completion.\n"
        "- **Efficient polling**: ETag support prevents unnecessary data transfer when job status hasn't changed.\n"
        "- **Error investigation**: Shows failure details and error messages for troubleshooting.\n"
        "- Without this endpoint, users would have no way to access job results or know when operations completed.\n\n"
        "**What it does:**\n"
        "- Returns the current status of a background job (queued, running, finished, failed, cancelled)\n"
        "- Includes the job result when complete\n"
        "- Supports efficient polling with conditional requests (ETag/304)\n\n"
        "**Access:**\n"
        "- Job owner (the user who created it) can always view\n"
        "- Admin users with `admin:all` permission can view any job\n"
        "- Other users get `404 Not Found` (anti-enumeration: can't tell if job exists)\n\n"
        "**Behavior:**\n"
        "- **Caching**: Returns `ETag` header based on job state. Use `If-None-Match` to get `304` when unchanged\n"
        "- **Privacy**: Non-owners get 404 instead of 403 to prevent job ID guessing\n"
        "- **Polling**: Recommended to poll every 1-2 seconds with ETag, or use SSE endpoint for real-time updates\n\n"
        "**Responses:**\n"
        "- 200: OK – Job details (id, status, type, owner, created_at, updated_at, result)\n"
        "- 304: Not Modified – Job hasn't changed since your last request (use cached data)\n"
        "- 400: Bad Request – Invalid job_id format (must be UUID)\n"
        "- 401: Unauthorized – Missing or invalid authentication token\n"
        "- 404: Not Found – Job doesn't exist, or you don't have permission to view it\n\n"
        "**Examples:**\n"
        "```bash\n"
        "# Get job status\n"
        "curl -X GET http://localhost:8000/v1/jobs/123e4567-e89b-12d3-a456-426614174000 \\\n"
        '     -H "Authorization: Bearer $TOKEN"\n\n'
        "# Efficient polling with ETag\n"
        "curl -X GET http://localhost:8000/v1/jobs/123e4567-e89b-12d3-a456-426614174000 \\\n"
        '     -H "Authorization: Bearer $TOKEN" \\\n'
        '     -H "If-None-Match: W/\\"abc123\\"" \\\n'
        "     -i  # Returns 304 if unchanged\n"
        "```"
    ),
    responses={
        200: {
            "description": "OK – current job representation returned",
            "headers": {
                "ETag": {
                    "schema": {"type": "string"},
                    "description": "Weak entity tag for the job JSON representation",
                    "example": 'W/"abc123def456"',
                },
                "Cache-Control": {"schema": {"type": "string"}, "example": "private, max-age=15"},
                "Vary": {"schema": {"type": "string"}, "example": "Authorization"},
                "X-Request-Id": {
                    "schema": {"type": "string"},
                    "description": "Unique identifier for this request (not the job ID)",
                    "example": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                },
            },
            "content": {
                "application/json": {
                    "example": {"id": "123e4567-e89b-12d3-a456-426614174000", "status": "running", "result": None}
                }
            },
        },
        304: {
            "description": "Not Modified – representation unchanged (no body). Returned when If-None-Match matches current ETag.",
            "headers": {
                "ETag": {
                    "schema": {"type": "string"},
                    "description": "Same ETag as sent in If-None-Match",
                    "example": 'W/"abc123def456"',
                },
                "Cache-Control": {"schema": {"type": "string"}, "example": "private, max-age=15"},
                "Vary": {"schema": {"type": "string"}, "example": "Authorization"},
                "X-Request-Id": {
                    "schema": {"type": "string"},
                    "description": "Unique identifier for this request",
                    "example": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                },
            },
        },
        401: {"description": "Unauthorized"},
        404: {"description": "Job not found or access denied"},
    },
)
async def get_job(
    job_id: str,
    request: Request,
    user=Depends(get_current_principal),
    db: Session = Depends(get_db) if POSTGRES_AVAILABLE else None,
) -> Response:
    """Return job metadata and final result when available.

    Access control: Allow job owner OR admin:all. Return 404 for unauthorized callers (anti-enumeration).
    """
    # Route to PostgreSQL backend if enabled
    if _use_postgres_backend() and db is not None:
        return await _get_job_postgres(
            job_id=job_id,
            request=request,
            user=user,
            db=db,
        )

    # Legacy implementation (memory/Redis store)
    # Validate UUID format first (400 if invalid)
    _validate_job_id_uuid(job_id)

    # Get job from store (feature flag determines backend)
    job_store_impl, _, _ = get_stores()
    job_doc = await job_store_impl.get(job_id)

    if not job_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    # Check if caller is owner or admin (anti-enumeration: 404 if not owner and not admin)
    _require_owner_or_admin(user, job_doc)

    # Extract owner for response
    caller_sub = principal_identity(user)
    job_owner = job_doc.owner

    # Build response using JobResponse model
    body_obj = JobResponse(
        id=job_id,
        type=job_doc.type,
        status=job_doc.status.value,
        created_at=job_doc.created_at.isoformat() + "Z"
        if not job_doc.created_at.isoformat().endswith("Z")
        else job_doc.created_at.isoformat(),
        updated_at=job_doc.updated_at.isoformat() + "Z"
        if job_doc.updated_at and not job_doc.updated_at.isoformat().endswith("Z")
        else (job_doc.updated_at.isoformat() if job_doc.updated_at else None),
        tenant_id=job_doc.tenant_id,
        owner=job_owner,
        result=job_doc.result,
    )
    body = body_obj.model_dump()

    # Compute ETag
    try:
        etag = compute_etag(body)
    except Exception:
        etag = None
    inm = request.headers.get("if-none-match")
    if etag and inm and inm.strip() == etag:
        # 304 Not Modified – minimal headers
        resp = Response(status_code=304)
        resp.headers["ETag"] = etag
        resp.headers["Cache-Control"] = "private, max-age=15"
        resp.headers["Vary"] = "Authorization"
        # X-Request-Id is set by middleware
        return resp
    # Normal 200 response
    with contextlib.suppress(Exception):
        record_provenance(
            actor="api",
            action="jobs.get",
            resource=f"/jobs/{job_id}",
            input={},
            output={"status": job_doc.status.value},
            meta={"user": caller_sub},
            success=True,
        )
    headers = {
        "Cache-Control": "private, max-age=15",
        "Vary": "Authorization",
        # X-Request-Id is set by middleware
    }
    if etag:
        headers["ETag"] = etag
    return JSONResponse(content=body, status_code=200, headers=headers)


# NOTE: list/HEAD handlers for /jobs have been moved to `src.routers.admin_jobs`
# to provide a single canonical admin-facing jobs list. Keeping create/get/cancel
# endpoints here for compact job operations.


@router.delete(
    "/{job_id}",
    name="cancel_job",
    summary="Cancel job (202 first, then idempotent 200)",
    description=(
        "DELETE /v1/jobs/{job_id} – Cancel a running or queued job\n\n"
        "**Why we need this endpoint:**\n"
        "- **Resource cleanup**: Stop unnecessary work and free up worker capacity for other jobs.\n"
        "- **User control**: Users need ability to abort jobs that were started by mistake or are no longer needed.\n"
        "- **Cost savings**: Cancelling long-running operations prevents wasted compute time and API costs.\n"
        "- **Retry safety**: Idempotent design means clients can safely retry cancellation without errors.\n"
        "- Without this endpoint, users would have no way to stop jobs, wasting resources on unwanted operations.\n\n"
        "**What it does:**\n"
        "- Cancels a background job that's queued or running\n"
        "- First successful cancel returns `202 Accepted`, subsequent calls return `200 OK`\n"
        "- Safe to retry (idempotent) – won't cause errors if already cancelled or finished\n\n"
        "**Access:**\n"
        "- Job owner can cancel their own jobs\n"
        "- Admin users with `admin:all` permission can cancel any job\n"
        "- Other users get `404 Not Found` (anti-enumeration)\n\n"
        "**Behavior:**\n"
        "- **Idempotency**: First cancel returns 202, all subsequent calls return 200 (safe to retry)\n"
        "- **Terminal states**: Already finished/failed/cancelled jobs return 200 with current status\n"
        "- **Atomicity**: Redis backend uses atomic Lua script for race-free cancellation\n"
        "- **Privacy**: Non-owners get 404 instead of 403 to prevent job ID guessing\n\n"
        "**Responses:**\n"
        "- 202: Accepted – Job successfully transitioned to 'cancelled' state\n"
        "- 200: OK – Job already in terminal state (cancelled, finished, or failed). Returns current status\n"
        "- 400: Bad Request – Invalid job_id format (must be UUID)\n"
        "- 401: Unauthorized – Missing or invalid authentication token\n"
        "- 404: Not Found – Job doesn't exist, or you don't have permission to cancel it\n\n"
        "**Examples:**\n"
        "```bash\n"
        "# Cancel a job\n"
        "curl -X DELETE http://localhost:8000/v1/jobs/123e4567-e89b-12d3-a456-426614174000 \\\n"
        '     -H "Authorization: Bearer $TOKEN"\n\n'
        "# Response (first time): 202 Accepted\n"
        '# {"id": "123e4567-e89b-12d3-a456-426614174000", "status": "cancelled"}\n\n'
        "# Response (retry): 200 OK\n"
        '# {"id": "123e4567-e89b-12d3-a456-426614174000", "status": "cancelled"}\n'
        "```"
    ),
    responses={
        202: {
            "description": "Accepted – cancellation applied",
            "headers": {
                "X-Request-Id": {"schema": {"type": "string"}},
                "Cache-Control": {"schema": {"type": "string"}},
            },
            "content": {"application/json": {"example": {"id": "...", "status": "cancelled"}}},
        },
        200: {
            "description": "OK – idempotent (already cancelled or finished)",
            "headers": {
                "X-Request-Id": {"schema": {"type": "string"}},
                "Cache-Control": {"schema": {"type": "string"}},
            },
            "content": {"application/json": {"example": {"id": "...", "status": "finished"}}},
        },
        401: {"description": "Unauthorized"},
        403: {"description": "Forbidden"},
        404: {"description": "Not Found"},
    },
)
async def cancel_job(
    job_id: str, user=Depends(get_current_principal), db: Session = Depends(get_db) if POSTGRES_AVAILABLE else None
) -> Response:
    from db.redis_cache.job_store import RedisJobStore
    from src.config import settings
    from src.jobs.factory import get_stores
    from src.jobs.models import JobStatus

    # Route to PostgreSQL backend if enabled
    if _use_postgres_backend() and db is not None:
        return await _cancel_job_postgres(
            job_id=job_id,
            user=user,
            db=db,
        )

    # Legacy implementation (memory/Redis store)
    # Validate UUID format first (400 if invalid)
    _validate_job_id_uuid(job_id)

    # --- Get store implementations based on feature flag ---
    job_store_impl, _, _ = get_stores()

    # Get current job
    job_doc = await job_store_impl.get(job_id)
    if not job_doc:
        raise HTTPException(status_code=404, detail="Job not found")

    # Check owner OR admin permission
    _require_owner_or_admin(user, job_doc)

    prev_status = job_doc.status
    first_cancel = False
    new_status = prev_status

    # Use atomic cancellation if Redis backend (safer for concurrent scenarios)
    if settings.JOB_STORE_BACKEND == "redis" and isinstance(job_store_impl, RedisJobStore):
        # Atomic Lua script handles CAS (compare-and-set) internally
        first_cancel = await job_store_impl.cancel_job_atomic(job_id)
        if first_cancel:
            new_status = JobStatus.CANCELLED
    # Fallback: traditional update_status (memory backend or non-atomic path)
    elif prev_status in (JobStatus.QUEUED, JobStatus.RUNNING):
        await job_store_impl.update_status(job_id=job_id, status=JobStatus.CANCELLED, result={"cancelled": True})
        first_cancel = True
        new_status = JobStatus.CANCELLED

    # provenance audit
    with contextlib.suppress(Exception):
        record_provenance(
            actor="api",
            action="jobs.cancel",
            resource=f"/jobs/{job_id}",
            input={},
            output={"from": prev_status.value, "to": new_status.value},
            meta={"user": principal_identity(user)},
            success=True,
        )

    status_code = 202 if first_cancel else 200
    body = {"id": job_id, "status": new_status.value}
    headers = {
        "Cache-Control": "no-store",
        # X-Request-Id is set by middleware
    }
    return JSONResponse(content=body, status_code=status_code, headers=headers)


def _require_job_manage(user) -> None:
    """Require admin:all permission (strict admin-only check)."""
    perms = set(current_permissions(user))
    # Harden RBAC: only allow explicit admin:all permission
    if "admin:all" not in perms:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: admin scope required")


def _require_owner_or_admin(user, job_doc) -> None:
    """Require caller to be job owner OR have admin:all permission."""
    caller_sub = principal_identity(user)
    job_owner = job_doc.owner
    perms = set(current_permissions(user))
    is_admin = "admin:all" in perms
    is_owner = caller_sub == job_owner

    if not is_owner and not is_admin:
        # Anti-enumeration: return 404 instead of 403
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")


# ============================================================================
# PostgreSQL Backend Implementation (New)
# ============================================================================


async def _create_job_postgres(
    req: JobRequest,
    request: Request,
    user,
    response: Response,
    db: Session,
) -> Response:
    """Create job using PostgreSQL backend."""
    from src.services.jobs_service import JobsService

    # Validate job type
    allowed_raw = getattr(settings, "ALLOWED_JOB_TYPES", None)
    try:
        allowed_types = [t.strip() for t in (allowed_raw or "demo").split(",") if t.strip()]
    except Exception:
        allowed_types = ["demo"]

    if req.type not in allowed_types:
        raise HTTPException(
            status_code=400, detail=f"unknown job type: {req.type}. Allowed: {', '.join(allowed_types)}"
        )

    # Get caller identity
    owner_sub = principal_identity(user)
    tenant_id = getattr(getattr(request, "state", None), "tenant_id", None) or "global"
    idem_key_hdr = (request.headers.get("Idempotency-Key") or "").strip() or None

    # Create job with idempotency check
    jobs_service = JobsService(db)
    try:
        job, is_new = jobs_service.create_job(
            owner_sub=owner_sub,
            tenant_id=tenant_id,
            job_type=req.type,
            payload=req.payload or {},
            idempotency_key=idem_key_hdr,
            priority=0,
        )
    except Exception as e:
        logger.error(f"Failed to create job: {e}")
        raise HTTPException(status_code=500, detail="Failed to create job")

    # Build response
    status_code = status.HTTP_202_ACCEPTED if is_new else status.HTTP_200_OK
    body = {
        "id": str(job.id),
        "status": job.status,
        "owner": job.owner_sub,
        "type": job.type,
        "created_at": job.created_at.isoformat() + "Z"
        if not job.created_at.isoformat().endswith("Z")
        else job.created_at.isoformat(),
    }

    # Build headers
    headers = {
        "Cache-Control": "no-store",
        "Idempotency-Replayed": "false" if is_new else "true",
    }

    if idem_key_hdr:
        headers["Idempotency-Key"] = idem_key_hdr

    # Add Location header
    try:
        loc = request.url_for("get_job", job_id=str(job.id))
        headers["Location"] = str(loc)
    except Exception:
        headers["Location"] = f"/v1/jobs/{job.id}"

    # Record provenance
    with contextlib.suppress(Exception):
        record_provenance(
            actor="api",
            action="jobs.create",
            resource="/jobs",
            input=req.model_dump(),
            output={"job_id": str(job.id)},
            meta={"user": owner_sub, "backend": "postgresql"},
            success=True,
        )

    return JSONResponse(content=body, status_code=status_code, headers=headers)


async def _list_jobs_postgres(
    request: Request,
    response: Response,
    user,
    db: Session,
    status_filter: list[str] | None = None,
    limit: int = 25,
    page_token: str | None = None,
) -> Response:
    """List jobs using PostgreSQL backend."""
    from src.services.jobs_service import JobsService

    # Get caller identity
    owner_sub = principal_identity(user)
    tenant_id = getattr(getattr(request, "state", None), "tenant_id", None) or "global"

    # Parse pagination offset
    offset = 0
    if page_token:
        try:
            offset = int(page_token)
            if offset < 0:
                raise HTTPException(status_code=400, detail="Invalid page_token: offset must be non-negative")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid page_token: must be a valid offset integer")

    # Parse status filter (PostgreSQL backend supports single status only for now)
    # Pass status filter as list (repository expects Optional[List[str]])
    status_list = status_filter if status_filter else None

    # List jobs via service layer
    jobs_service = JobsService(db)
    try:
        jobs, total, has_more = jobs_service.list_jobs(
            owner_sub=owner_sub,
            tenant_id=tenant_id,
            status=status_list,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        logger.error(f"Failed to list jobs: {e}")
        raise HTTPException(status_code=500, detail="Failed to list jobs")

    # Validate page_token bounds
    if page_token and offset >= total and total > 0:
        raise HTTPException(status_code=400, detail=f"Invalid page_token: offset {offset} exceeds total {total}")

    # Build response items
    items = []
    for job in jobs:
        job_dict = job.to_dict(include_payload=False, include_result=True)
        items.append(
            JobResponse(
                id=str(job.id),
                type=job.type,
                status=job.status,
                created_at=job.created_at.isoformat() + "Z"
                if not job.created_at.isoformat().endswith("Z")
                else job.created_at.isoformat(),
                updated_at=job.updated_at.isoformat() + "Z"
                if job.updated_at and not job.updated_at.isoformat().endswith("Z")
                else (job.updated_at.isoformat() if job.updated_at else None),
                tenant_id=job.tenant_id,
                owner=job.owner_sub,
                result=job_dict.get("result"),
            )
        )

    # Compute next page token
    next_token = str(offset + len(jobs)) if has_more else None

    result_body = JobListResponse(
        items=items,
        next_page_token=next_token,
        has_more=has_more,
        total=total,
    )

    # Compute ETag using JobsService
    try:
        etag = jobs_service.compute_list_etag(
            owner_sub=owner_sub,
            tenant_id=tenant_id,
            status=status_list,
        )
    except Exception:
        # Fallback to simple hash
        import hashlib

        body_dict = result_body.model_dump()
        etag_context = {
            "route": "user_jobs",
            "owner": owner_sub,
            "tenant": tenant_id,
            "filters": {"status": status_filter},
        }
        etag_str = str(body_dict) + str(etag_context)
        etag = hashlib.md5(etag_str.encode(), usedforsecurity=False).hexdigest()

    # Check If-None-Match for 304
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
    body_dict = result_body.model_dump()
    return JSONResponse(
        content=body_dict,
        status_code=200,
        headers={
            "ETag": etag,
            "Cache-Control": "private, max-age=30",
            "Vary": "Authorization",
        },
    )


async def _get_job_postgres(
    job_id: str,
    request: Request,
    user,
    db: Session,
) -> Response:
    """Get job using PostgreSQL backend."""
    from src.services.jobs_service import JobsService

    # Validate UUID format
    _validate_job_id_uuid(job_id)

    # Get caller identity and permissions
    owner_sub = principal_identity(user)
    perms = set(current_permissions(user))
    is_admin = "admin:all" in perms

    # Get job via service layer
    jobs_service = JobsService(db)
    try:
        if is_admin:
            # Admin can access any job - use repository directly
            job = jobs_service.repo.get_job(job_id)
        else:
            # Regular user - owner-scoped access
            job = jobs_service.get_job(job_id, owner_sub)

        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get job {job_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get job")

    # Build response
    job_dict = job.to_dict(include_payload=False, include_result=True)
    body_obj = JobResponse(
        id=str(job.id),
        type=job.type,
        status=job.status,
        created_at=job.created_at.isoformat() + "Z"
        if not job.created_at.isoformat().endswith("Z")
        else job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat() + "Z"
        if job.updated_at and not job.updated_at.isoformat().endswith("Z")
        else (job.updated_at.isoformat() if job.updated_at else None),
        tenant_id=job.tenant_id,
        owner=job.owner_sub,
        result=job_dict.get("result"),
    )
    body = body_obj.model_dump()

    # Use job's built-in ETag
    etag = job.etag

    # Check If-None-Match for 304
    if_none_match = request.headers.get("if-none-match", "").strip()
    if etag and if_none_match == etag:
        return Response(
            status_code=304,
            headers={
                "ETag": etag,
                "Cache-Control": "private, max-age=15",
                "Vary": "Authorization",
            },
        )

    # Record provenance
    with contextlib.suppress(Exception):
        record_provenance(
            actor="api",
            action="jobs.get",
            resource=f"/jobs/{job_id}",
            input={},
            output={"status": job.status},
            meta={"user": owner_sub, "backend": "postgresql"},
            success=True,
        )

    # Return 200
    headers = {
        "Cache-Control": "private, max-age=15",
        "Vary": "Authorization",
    }
    if etag:
        headers["ETag"] = etag

    return JSONResponse(content=body, status_code=200, headers=headers)


async def _cancel_job_postgres(
    job_id: str,
    user,
    db: Session,
) -> Response:
    """Cancel job using PostgreSQL backend."""
    from uuid import UUID

    from src.services.jobs_service import JobsService

    # Validate UUID format
    _validate_job_id_uuid(job_id)
    job_uuid = UUID(job_id)

    # Get caller identity and permissions
    owner_sub = principal_identity(user)
    perms = set(current_permissions(user))
    is_admin = "admin:all" in perms

    # Get job first to verify access
    jobs_service = JobsService(db)
    job = None
    try:
        if is_admin:
            # Admin can cancel any job
            logger.info(f"Admin cancelling job {job_uuid}")
            job = jobs_service.repo.get_job(job_uuid)
            logger.info(f"Admin got job: {job is not None}")
        else:
            # Regular user - owner-scoped access
            logger.info(f"User {owner_sub} cancelling job {job_uuid}")
            job = jobs_service.get_job(job_uuid, owner_sub)
            logger.info(f"User got job: {job is not None}")

        if not job:
            logger.warning(f"Job {job_uuid} not found")
            raise HTTPException(status_code=404, detail="Job not found")

        logger.info(f"Job found, owner: {job.owner_sub if job else 'NONE'}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get job {job_id} for cancellation: {e}")
        raise HTTPException(status_code=500, detail="Failed to cancel job")

    # At this point, job must exist (or we would have raised 404/500)
    # Cancel the job
    try:
        owner_for_cancel = owner_sub if not is_admin else (job.owner_sub if job else owner_sub)
        logger.info(f"Cancelling with owner: {owner_for_cancel}")
        cancelled_job, first_cancel = jobs_service.cancel_job(job_uuid, owner_for_cancel)
    except Exception as e:
        logger.error(f"Failed to cancel job {job_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to cancel job")

    # Record provenance
    with contextlib.suppress(Exception):
        record_provenance(
            actor="api",
            action="jobs.cancel",
            resource=f"/jobs/{job_id}",
            input={},
            output={"status": cancelled_job.status},
            meta={"user": owner_sub, "backend": "postgresql", "first_cancel": first_cancel},
            success=True,
        )

    # Return response
    status_code = 202 if first_cancel else 200
    body = {"id": str(cancelled_job.id), "status": cancelled_job.status}
    headers = {"Cache-Control": "no-store"}

    return JSONResponse(content=body, status_code=status_code, headers=headers)


async def _stream_job_events_postgres(
    job_id: str,
    request: Request,
    user,
    db: Session,
    retry_ms: int = 5000,
    last_event_id: int | None = None,
) -> StreamingResponse:
    """Stream job events using PostgreSQL backend with SSE."""
    import time
    from uuid import UUID

    from src.services.jobs_service import JobsService

    # Validate and convert job_id
    _validate_job_id_uuid(job_id)
    job_uuid = UUID(job_id)

    # Get caller identity and permissions
    owner_sub = principal_identity(user)
    perms = set(current_permissions(user))
    is_admin = "admin:all" in perms

    # Verify job exists and check permissions
    jobs_service = JobsService(db)
    try:
        if is_admin:
            job = jobs_service.repo.get_job(job_uuid)
        else:
            job = jobs_service.get_job(job_uuid, owner_sub)

        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get job {job_id} for events stream: {e}")
        raise HTTPException(status_code=500, detail="Failed to stream events")

    async def event_generator():
        nonlocal last_event_id
        last_seen = int(last_event_id) if last_event_id else 0

        # Always send initial retry directive
        yield f"retry: {retry_ms}\n"

        # Get all events from PostgreSQL to determine starting seq
        all_events = jobs_service.get_events(job_uuid, after_seq_id=0, limit=10000)
        seq = 1

        # Replay missed events from PostgreSQL
        if last_seen > 0:
            try:
                events_to_replay = [e for e in all_events if e.seq_id > last_seen]
                if events_to_replay:
                    for event in events_to_replay:
                        # Convert JobEvent to SSE format
                        event_data = event.event_json or {}
                        yield f"id: {event.seq_id}\nevent: {event.event_type}\ndata: {json.dumps(event_data)}\n\n"
                        seq = event.seq_id + 1
                else:
                    yield f": no-backlog-replay-from {last_seen}\n"
                    # Set seq to last seen + 1 or max(existing events) + 1
                    seq = max(e.seq_id for e in all_events) + 1 if all_events else last_seen + 1
            except Exception as e:
                logger.warning(f"Failed to replay events: {e}")
                yield f": no-backlog-replay-from {last_seen}\n"
                if all_events:
                    seq = max(e.seq_id for e in all_events) + 1
        # First connection - send all existing events
        elif all_events:
            for event in all_events:
                event_data = event.event_json or {}
                yield f"id: {event.seq_id}\nevent: {event.event_type}\ndata: {json.dumps(event_data)}\n\n"
                seq = event.seq_id + 1
        else:
            # No events yet, send initial status
            status_payload = json.dumps(
                {
                    "job_id": job_id,
                    "status": job.status,
                    "created_at": job.created_at.isoformat() if job.created_at else None,
                }
            )
            yield f"id: {seq}\nevent: status\ndata: {status_payload}\n\n"
            seq += 1

        # Heartbeat configuration
        try:
            heartbeat_interval = int(getattr(settings, "JOB_SSE_HEARTBEAT_SECS", 15))
        except Exception:
            heartbeat_interval = 15
        last_hb = time.time()

        # Poll for new events and status changes
        last_status = job.status
        poll_interval = 1.0  # Poll every 1 second
        max_iterations = 300  # Max 5 minutes (300 seconds)
        iteration = 0

        try:
            while iteration < max_iterations:
                iteration += 1

                # Emit heartbeat if needed
                now = time.time()
                if now - last_hb >= heartbeat_interval:
                    last_hb = now
                    yield f": heartbeat {seq}\n"

                # Refresh job from database
                try:
                    job = jobs_service.repo.get_job(job_uuid)
                    if not job:
                        # Job was deleted
                        error_payload = json.dumps({"error": "job not found"})
                        yield f"id: {seq}\nevent: error\ndata: {error_payload}\n\n"
                        break

                    # Check for status change
                    if job.status != last_status:
                        status_payload = json.dumps(
                            {
                                "job_id": job_id,
                                "status": job.status,
                                "updated_at": job.updated_at.isoformat() if job.updated_at else None,
                            }
                        )
                        yield f"id: {seq}\nevent: status\ndata: {status_payload}\n\n"
                        last_status = job.status
                        seq += 1

                    # Get new events since last check
                    new_events = jobs_service.get_events(job_uuid, after_seq_id=seq - 1, limit=100)
                    for event in new_events:
                        if event.seq_id >= seq:
                            event_data = event.event_json or {}
                            yield f"id: {event.seq_id}\nevent: {event.event_type}\ndata: {json.dumps(event_data)}\n\n"
                            seq = event.seq_id + 1

                    # Check if job is terminal
                    if job.is_terminal():
                        # Send final end event
                        end_payload = json.dumps(
                            {
                                "job_id": job_id,
                                "final": job.status,
                                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                            }
                        )
                        yield f"id: {seq}\nevent: end\ndata: {end_payload}\n\n"
                        break

                except Exception as e:
                    logger.error(f"Error polling job {job_id}: {e}")
                    # Continue polling on transient errors

                # Wait before next poll
                await asyncio.sleep(poll_interval)

            # If we hit max iterations, send end event
            if iteration >= max_iterations:
                timeout_payload = json.dumps(
                    {"job_id": job_id, "final": job.status if job else "unknown", "reason": "stream_timeout"}
                )
                yield f"id: {seq}\nevent: end\ndata: {timeout_payload}\n\n"

        except Exception as e:
            logger.error(f"Error in event stream for job {job_id}: {e}")
            error_payload = json.dumps({"error": str(e)})
            yield f"id: {seq}\nevent: error\ndata: {error_payload}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create a background job (idempotent)",
    description=(
        "POST /v1/jobs – Submit a new background job\n\n"
        "**Why we need this endpoint:**\n"
        "- **Async operations**: Long-running tasks shouldn't block API requests; this endpoint queues work and returns immediately.\n"
        "- **Scalability**: Background jobs can be processed by separate worker services, allowing the API to remain responsive.\n"
        "- **Retry safety**: With idempotency keys, clients can safely retry failed requests without creating duplicate jobs.\n"
        "- **Job tracking**: Returns job ID so clients can monitor progress, retrieve results, or cancel if needed.\n"
        "- Without this endpoint, all operations would be synchronous, causing timeouts and blocking other users' requests.\n\n"
        "**What it does:**\n"
        "- Creates a new background job and returns immediately (doesn't wait for completion)\n"
        "- Returns job ID and status URL so you can poll or stream progress\n"
        "- Automatically deduplicates identical requests (idempotency)\n\n"
        "**Access:**\n"
        "- Any authenticated user can create jobs\n"
        "- Job owner is automatically set to your token subject (sub claim)\n"
        "- No admin permission required\n\n"
        "**Behavior:**\n"
        "- **Idempotency**: Send `Idempotency-Key` header to prevent duplicate jobs. Same key within 24h returns existing job (200 OK) instead of creating new one (202 Accepted)\n"
        "- **Auto-deduplication**: Even without explicit key, identical payload from same user is deduplicated\n"
        "- **Job types**: Must be in allowed list (e.g., 'demo', 'test'). Check API config for valid types\n"
        "- **Retention**: Jobs auto-expire after creation (Redis: 10 days TTL, Memory: 7 days background sweep)\n"
        "- **Backend**: Configure via `JOB_STORE_BACKEND` env (memory or redis)\n\n"
        "**Responses:**\n"
        '- 202: Accepted – New job created successfully. Returns `{"id": "...", "status": "queued", "owner": "you@example.com"}`\n'
        "- 200: OK – Idempotent replay (same request already processed). Returns existing job with `Idempotency-Replayed: true` header\n"
        "- 400: Bad Request – Unknown job type or invalid payload schema\n"
        "- 401: Unauthorized – Missing or invalid authentication token\n"
        "- 422: Validation Error – Malformed request body\n\n"
        "**Examples:**\n"
        "```bash\n"
        "# Create a new job\n"
        "curl -X POST http://localhost:8000/v1/jobs \\\n"
        '     -H "Authorization: Bearer $TOKEN" \\\n'
        '     -H "Content-Type: application/json" \\\n'
        '     -d \'{"type": "demo", "payload": {"duration_ms": 2000}}\'\n\n'
        "# Create with idempotency key (safe retry)\n"
        "curl -X POST http://localhost:8000/v1/jobs \\\n"
        '     -H "Authorization: Bearer $TOKEN" \\\n'
        '     -H "Content-Type: application/json" \\\n'
        '     -H "Idempotency-Key: my-unique-key-123" \\\n'
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
                "application/json": {
                    "example": {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "status": "queued",
                        "owner": "user@example.com",
                    }
                }
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
                "application/json": {
                    "example": {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "status": "queued",
                        "owner": "user@example.com",
                    }
                }
            },
        },
        400: {"description": "Bad Request – unknown job type or payload schema violation (problem+json)"},
        401: {"description": "Unauthorized"},
        403: {"description": "Forbidden"},
        422: {"description": "Validation Error (invalid body structure)"},
        500: {"description": "Internal Server Error"},
    },
)
async def create_job(
    req: JobRequest,
    request: Request,
    user=Depends(get_current_principal),
    response: Response = None,
    db: Session = Depends(get_db) if POSTGRES_AVAILABLE else None,
):
    """Enqueue a canonical background job.

    The API returns immediately with 202 and a Location header to poll the job. Use `Idempotency-Key` to safely retry job creation without duplicating work.

    Owner is automatically set to the authenticated user's token subject.
    """
    # Any authenticated user can create jobs - no admin:all required

    # --- PostgreSQL backend (new) ---
    if _use_postgres_backend() and db is not None:
        return await _create_job_postgres(req, request, user, response, db)

    # --- Legacy memory/Redis backend ---
    # Get store implementations based on feature flag
    job_store_impl, idem_store, event_store = get_stores()

    # --- Validate type against allowed list (configurable) ---
    allowed_raw = getattr(settings, "ALLOWED_JOB_TYPES", None)
    try:
        allowed_types = [t.strip() for t in (allowed_raw or "demo").split(",") if t.strip()]
    except Exception:
        allowed_types = ["demo"]
    if req.type not in allowed_types:
        # Attach extension metadata to help clients introspect supported types
        exc = HTTPException(status_code=400, detail=f"unknown job type: {req.type}")
        try:
            exc.extensions_extra = {  # type: ignore[attr-defined]
                "allowed_types": allowed_types,
                "reason": "unknown_type",
            }
        except Exception:
            pass
        raise exc

    # Optional per-type payload schema validation hooks
    # Define built-in schemas for demo, test, long-running, and agent.run types
    SCHEMAS: dict[str, dict[str, Any]] = {
        "demo": {
            "type": "object",
            "properties": {
                "duration_ms": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "Optional simulation duration in milliseconds",
                }
            },
            "additionalProperties": True,
        },
        "test": {
            "type": "object",
            "properties": {
                "duration_ms": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "Optional simulation duration in milliseconds",
                },
                "should_fail": {"type": "boolean", "description": "If true, job will fail instead of succeed"},
            },
            "additionalProperties": True,
        },
        "long-running": {
            "type": "object",
            "properties": {
                "duration_ms": {
                    "type": "integer",
                    "minimum": 5000,
                    "description": "Duration in milliseconds (min 5000ms/5s)",
                }
            },
            "required": ["duration_ms"],
            "additionalProperties": True,
        },
        "agent.run": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "minLength": 1,
                    "description": "The user's prompt/goal for the agent (required)",
                },
                "user_id": {
                    "type": "string",
                    "minLength": 1,
                    "description": "User ID from JWT subject (required)",
                },
                "tenant_id": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Tenant identifier (required)",
                },
                "session_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "Session UUID for context persistence (optional)",
                },
                "run_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "Pre-generated run ID (optional)",
                },
                "model": {
                    "type": "string",
                    "description": "Specific model to use (optional, overrides default)",
                },
                "manager": {
                    "type": "string",
                    "description": "Manager/planner LLM client name (optional)",
                },
                "temperature": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 2.0,
                    "default": 0.2,
                    "description": "Sampling temperature (optional, default: 0.2)",
                },
                "max_steps": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 50,
                    "default": 8,
                    "description": "Maximum orchestration steps (optional, default: 8)",
                },
                "metadata": {
                    "type": "object",
                    "description": "Arbitrary metadata to persist with the run (optional)",
                },
                "trace_id": {
                    "type": "string",
                    "description": "Distributed trace ID for observability (optional)",
                },
                "request_id": {
                    "type": "string",
                    "description": "HTTP request ID for correlation (optional)",
                },
                "principal": {
                    "type": "object",
                    "description": "Principal context from JWT (optional, populated by API)",
                },
            },
            "required": ["prompt", "user_id", "tenant_id"],
            "additionalProperties": True,
        },
    }
    try:
        extra = getattr(settings, "JOB_PAYLOAD_SCHEMAS", None)
        if isinstance(extra, dict):
            SCHEMAS.update({str(k): v for k, v in extra.items() if isinstance(v, dict)})
    except Exception:
        pass
    schema = SCHEMAS.get(req.type)
    if schema is not None:
        try:
            from jsonschema import validate as js_validate

            js_validate(instance=req.payload or {}, schema=schema)
        except Exception as e:
            # Provide schema violation context
            msg = getattr(e, "message", str(e))
            exc = HTTPException(status_code=400, detail=f"invalid payload: {msg}")
            try:
                exc.extensions_extra = {  # type: ignore[attr-defined]
                    "reason": "schema_violation",
                    "schema_id": req.type,
                    "error": msg,
                }
            except Exception:
                pass
            raise exc

    # --- Idempotency (24h) using new store abstraction ---
    tenant = getattr(getattr(request, "state", None), "tenant_id", None) or "global"
    subj = principal_identity(user)

    # Build idempotency key using new helper
    idem_key_hdr = (request.headers.get("Idempotency-Key") or "").strip()
    idem_key = create_idempotency_key(
        owner=subj,
        tenant=tenant,
        job_type=req.type,
        payload=req.payload or {},
        idempotency_key=idem_key_hdr or None,
    )

    # Check for existing job (idempotency replay)
    existing_job_id = await idem_store.get_job_id(idem_key)

    status_code = status.HTTP_202_ACCEPTED
    replayed = False

    if existing_job_id:
        # Idempotency hit: return existing job
        job_id = existing_job_id
        replayed = True
        status_code = status.HTTP_200_OK
    else:
        # Create new job
        job_id = str(uuid.uuid4())
        created_at = datetime.utcnow()

        # Compute TTL
        ttl_days = settings.JOB_TTL_DAYS
        ttl_seconds = ttl_days * 86400

        # Build JobDocument
        job_doc = JobDocument(
            id=job_id,
            owner=subj,
            tenant_id=tenant,
            type=req.type,
            status=JobStatus.QUEUED,
            payload=req.payload or {},
            result=None,
            created_at=created_at,
            updated_at=None,
            error=None,
        )

        # Store job atomically
        await job_store_impl.create(job_doc, ttl_seconds=ttl_seconds)

        # Get next event ID and append initial "queued" event
        event_id = await event_store.get_next_event_id(job_id)
        queued_event = SSEEvent(
            event_id=event_id,
            event_type="status",
            data={"status": "queued", "job_id": job_id},
        )
        await event_store.append(job_id, queued_event, ring_size=settings.SSE_RING_SIZE)

        # Store idempotency mapping
        idem_ttl_seconds = settings.IDEMPOTENCY_TTL_HOURS * 3600
        await idem_store.store(idem_key, job_id, ttl_seconds=idem_ttl_seconds)

        # Start background worker (keep threading model, use async shim)
        def _runner(jid: str, payload: dict, stores):
            """Background worker using store abstractions."""
            job_st, _idem_st, event_st = stores

            try:
                # Transition to RUNNING
                _run_async(job_st.update_status(jid, JobStatus.RUNNING))

                ev_id = _run_async(event_st.get_next_event_id(jid))
                running_event = SSEEvent(
                    event_id=ev_id,
                    event_type="status",
                    data={"status": "running", "job_id": jid},
                )
                _run_async(event_st.append(jid, running_event, ring_size=settings.SSE_RING_SIZE))

                # Publish to Redis pub/sub for live SSE (legacy compatibility)
                try:
                    r = get_redis()
                    r.publish(f"jobs:{jid}", json.dumps({"event": "status", "job_id": jid, "status": "running"}))
                except Exception:
                    pass

                # Simulate work
                import time as _t

                try:
                    if isinstance(payload, dict) and "duration_ms" in payload:
                        sim_ms = int(payload["duration_ms"])
                    else:
                        sim_ms = int(getattr(settings, "JOB_SIM_SLEEP_MS", 100))
                except Exception:
                    sim_ms = 100
                sim_ms = max(sim_ms, 0)
                _t.sleep(sim_ms / 1000.0)

                # Check if job should fail
                should_fail = False
                if isinstance(payload, dict):
                    should_fail = payload.get("should_fail", False)

                if should_fail:
                    # Transition to FAILED
                    result = {"error": "Job configured to fail", "test_mode": True}
                    _run_async(
                        job_st.update_status(
                            jid,
                            JobStatus.FAILED,
                            result=result,
                            error="Job configured to fail",
                            ttl_seconds=ttl_seconds,
                        )
                    )

                    ev_id = _run_async(event_st.get_next_event_id(jid))
                    failed_event = SSEEvent(
                        event_id=ev_id,
                        event_type="status",
                        data={"status": "failed", "job_id": jid, "error": "Job configured to fail"},
                    )
                    _run_async(event_st.append(jid, failed_event, ring_size=settings.SSE_RING_SIZE))

                    final_status = "failed"
                else:
                    # Transition to FINISHED
                    result = {"ok": True, "duration_ms": sim_ms}
                    _run_async(
                        job_st.update_status(
                            jid,
                            JobStatus.FINISHED,
                            result=result,
                            ttl_seconds=ttl_seconds,
                        )
                    )

                    ev_id = _run_async(event_st.get_next_event_id(jid))
                    finished_event = SSEEvent(
                        event_id=ev_id,
                        event_type="status",
                        data={"status": "finished", "job_id": jid, "result": result},
                    )
                    _run_async(event_st.append(jid, finished_event, ring_size=settings.SSE_RING_SIZE))

                    final_status = "finished"

                # Append terminal "end" event
                ev_id = _run_async(event_st.get_next_event_id(jid))
                end_event = SSEEvent(
                    event_id=ev_id,
                    event_type="end",
                    data={"job_id": jid, "final": final_status},
                )
                _run_async(event_st.append(jid, end_event, ring_size=settings.SSE_RING_SIZE))

                # Publish to Redis pub/sub
                try:
                    r = get_redis()
                    r.publish(f"jobs:{jid}", json.dumps({"event": "status", "job_id": jid, "status": final_status}))
                except Exception:
                    pass

            except Exception as worker_err:
                # Ensure job state updated on unexpected error
                with contextlib.suppress(Exception):
                    _run_async(
                        job_st.update_status(
                            jid,
                            JobStatus.FAILED,
                            result={"ok": False},
                            error=str(worker_err),
                        )
                    )

        # Start worker thread with store instances
        import threading

        stores_tuple = (job_store_impl, idem_store, event_store)
        t = threading.Thread(target=_runner, args=(job_id, req.payload, stores_tuple), daemon=True)
        t.start()

    # Record provenance
    record_provenance(
        actor="api",
        action="jobs.create",
        resource="/jobs",
        input=req.model_dump(),
        output={"job_id": job_id},
        meta={"user": principal_identity(user)},
        success=True,
    )

    # Return with Location header
    body = {"id": job_id, "status": "queued", "owner": subj}
    headers = {
        "Cache-Control": "no-store",
        "Idempotency-Replayed": "true" if replayed else "false",
    }

    # Echo Idempotency-Key on both 202 (fresh) and 200 (replayed) responses
    if idem_key_hdr:
        headers["Idempotency-Key"] = idem_key_hdr

    try:
        # Build a version-agnostic Location using the registered route name
        try:
            loc = request.url_for("get_job", job_id=job_id)
        except Exception:
            # fallback to app.url_path_for if Request.url_for not available
            try:
                loc = request.app.url_path_for("get_job", job_id=job_id)
            except Exception:
                loc = f"/v1/jobs/{job_id}"
        headers["Location"] = str(loc)
    except Exception:
        pass

    # X-Request-Id is set by middleware (unique per request, not job_id)
    return JSONResponse(content=body, status_code=status_code, headers=headers)


# Colon-style alias for create action: POST /v1/jobs:create
@router.post(
    path=":create",
    include_in_schema=False,
)
async def create_job_colon(req: JobRequest, request: Request, user=Depends(get_current_principal)):
    # Delegate to the canonical implementation; letting FastAPI validate `req`
    return await create_job(req, request, user)


@router.get(
    "/{job_id}/events",
    name="job_events",
    response_class=StreamingResponse,
    summary="Stream job events (SSE with resume, heartbeats, final end)",
    description=(
        "GET /v1/jobs/{job_id}/events – Real-time job progress via Server-Sent Events (SSE)\n\n"
        "**Why we need this endpoint:**\n"
        "- **Real-time updates**: Users get instant notifications when job status changes, avoiding constant polling.\n"
        "- **Better UX**: Front-end apps can show live progress bars, status updates, and completion notifications.\n"
        "- **Network efficiency**: Single persistent connection is more efficient than polling every second.\n"
        "- **Reliable delivery**: Resume capability ensures clients don't miss events even after disconnections.\n"
        "- Without this endpoint, users would need to poll repeatedly, wasting bandwidth and missing instant updates.\n\n"
        "**What it does:**\n"
        "- Opens a persistent HTTP connection that streams job updates in real-time\n"
        "- Sends events when job status changes (queued → running → finished/failed/cancelled)\n"
        "- Includes heartbeats every 15 seconds to keep connection alive\n"
        "- Automatically closes after job reaches terminal state (finished/failed/cancelled)\n\n"
        "**Access:**\n"
        "- Job owner can stream their own jobs\n"
        "- Admin users with `admin:all` permission can stream any job\n"
        "- Other users get `404 Not Found` (anti-enumeration)\n\n"
        "**Behavior:**\n"
        "- **Protocol**: Standard Server-Sent Events (text/event-stream). Works with EventSource API in browsers\n"
        "- **Resume**: Send `Last-Event-ID` header to resume from last received event (uses ring buffer, 100 events)\n"
        "- **Retry**: Server sends `retry: 5000` (5s default, configurable via `?retry_ms=3000` query param)\n"
        "- **Heartbeats**: Comment lines `: heartbeat <n>` every 15s while job is active\n"
        "- **Terminal**: After final status event, server sends `event: end` and closes connection\n"
        "- **Backlog**: If you missed too many events (ring buffer rotated), server sends `: no-backlog-replay-from <id>` comment\n"
        "- **Redis backend**: Events stored in Redis (durable, works across multiple servers). **Recommended for production**\n"
        "- **Memory backend**: Events stored in-process (single-server only, lost on restart)\n\n"
        "**Responses:**\n"
        "- 200: OK – SSE stream established (content-type: text/event-stream)\n"
        "- 400: Bad Request – Invalid job_id (not UUID) or retry_ms out of range (1000-60000)\n"
        "- 401: Unauthorized – Missing or invalid authentication token\n"
        "- 404: Not Found – Job doesn't exist, or you don't have permission\n"
        "- 406: Not Acceptable – Client explicitly requested wrong content type (must accept text/event-stream)\n\n"
        "**Examples:**\n"
        "```bash\n"
        "# Stream events (keeps connection open)\n"
        "curl -N http://localhost:8000/v1/jobs/123e4567-e89b-12d3-a456-426614174000/events \\\n"
        '     -H "Authorization: Bearer $TOKEN"\n\n'
        "# With custom retry interval\n"
        'curl -N "http://localhost:8000/v1/jobs/123e4567-e89b-12d3-a456-426614174000/events?retry_ms=10000" \\\n'
        '     -H "Authorization: Bearer $TOKEN"\n\n'
        "# Resume from event ID 42\n"
        "curl -N http://localhost:8000/v1/jobs/123e4567-e89b-12d3-a456-426614174000/events \\\n"
        '     -H "Authorization: Bearer $TOKEN" \\\n'
        '     -H "Last-Event-ID: 42"\n\n'
        "# Example output:\n"
        "# retry: 5000\n"
        "# id: 1\n"
        "# event: status\n"
        '# data: {"job_id": "123e4567...", "status": "running"}\n'
        "#\n"
        "# : heartbeat 1\n"
        "# id: 2\n"
        "# event: end\n"
        '# data: {"job_id": "123e4567...", "final": "finished"}\n'
        "```"
    ),
    responses={
        200: {
            "description": "text/event-stream (SSE stream established)",
            "headers": {
                "Content-Type": {"schema": {"type": "string"}, "example": "text/event-stream; charset=utf-8"},
                "Cache-Control": {"schema": {"type": "string"}, "description": "Always 'no-store' for SSE streams"},
                "Connection": {
                    "schema": {"type": "string"},
                    "description": "Always 'keep-alive' for persistent connection",
                },
                "X-Request-Id": {"schema": {"type": "string"}, "description": "Unique identifier for this request"},
                "X-Accel-Buffering": {
                    "schema": {"type": "string"},
                    "description": "Always 'no' to discourage proxy buffering",
                },
                "Access-Control-Expose-Headers": {
                    "schema": {"type": "string"},
                    "description": "Exposes X-Request-Id for CORS clients",
                },
            },
            "content": {
                "text/event-stream": {
                    "schema": {"type": "string"},
                    "example": (
                        "retry: 5000\n"
                        ": no-backlog-replay-from 42\n"
                        "id: 1\n"
                        "event: status\n"
                        'data: {"job_id": "123e4567...", "status": "running"}\n\n'
                        ": heartbeat 1\n"
                        "id: 2\n"
                        "event: end\n"
                        'data: {"job_id": "123e4567...", "final": "finished"}\n\n'
                    ),
                }
            },
        },
        400: {"description": "Bad Request – malformed job_id (not a UUID) or invalid retry_ms"},
        401: {"description": "Unauthorized"},
        403: {"description": "Forbidden – requires owner OR admin:all permission"},
        404: {"description": "Job not found (or caller is not owner and lacks admin:all)"},
        406: {
            "description": "Not Acceptable – client explicitly requested incompatible media type (must accept text/event-stream or */*)"
        },
    },
)
async def job_events(
    job_id: str,
    request: Request,
    user=Depends(get_current_principal),
    retry_ms: int = Query(
        default=5000,
        ge=1000,
        le=60000,
        description="Override initial retry: directive in milliseconds (1000-60000)",
        examples=[5000, 10000, 30000],
    ),
    last_event_id: int | None = Header(
        default=None,
        alias="Last-Event-ID",
        description="Best-effort resume cursor; server replays buffered events with id > this value when available",
        examples=[42, 100, 250],
    ),
    db: Session = Depends(get_db) if POSTGRES_AVAILABLE else None,
):
    """Server-Sent Events endpoint streaming job progress.

    Keep the HTTP connection open to receive SSE messages. Each message payload is a JSON-encoded event indicating the job status or other progress information. If Redis is available the stream will subscribe to `jobs:{job_id}` channel for real-time updates; otherwise the endpoint sends the current status once and closes.

    Requires owner OR admin:all permission.
    """
    # Validate UUID format first (400 if invalid)
    _validate_job_id_uuid(job_id)

    # Validate Accept header - default to text/event-stream if missing or */*
    # Only reject if client explicitly requests incompatible media type
    accept_header = request.headers.get("accept", "").lower()
    if accept_header and accept_header != "*/*":
        # Client specified explicit media types - ensure text/event-stream is acceptable
        if "text/event-stream" not in accept_header and "*/*" not in accept_header:
            raise HTTPException(
                status_code=406,
                detail="Not Acceptable: this endpoint only returns text/event-stream. Omit Accept header or set Accept: text/event-stream.",
            )

    # Use PostgreSQL backend if enabled
    if _use_postgres_backend() and db is not None:
        return await _stream_job_events_postgres(
            job_id=job_id,
            request=request,
            user=user,
            db=db,
            retry_ms=retry_ms,
            last_event_id=last_event_id,
        )

    # --- Get store implementations and check permissions BEFORE streaming starts ---
    from src.jobs.factory import get_stores

    job_store_impl, _, event_store_impl = get_stores()

    # Check job exists and enforce owner OR admin permission
    job_doc = await job_store_impl.get(job_id)
    if not job_doc:
        raise HTTPException(status_code=404, detail="Job not found")
    _require_owner_or_admin(user, job_doc)

    async def event_generator():
        from src.jobs.models import SSEEvent

        last_seen = int(last_event_id) if last_event_id else 0
        seq = (last_seen + 1) if last_seen else 1

        # Always send initial retry directive
        yield f"retry: {retry_ms}\n"

        # Best-effort replay from event store ring buffer
        replayed = False
        if last_seen:
            try:
                events = await event_store_impl.list(job_id)
                if events:
                    missed = [e for e in events if e.id > last_seen]
                    if missed:
                        for ev in missed:
                            payload = ev.data
                            ev_type = ev.event_type
                            ev_id = ev.id
                            yield f"id: {ev_id}\nevent: {ev_type}\ndata: {payload}\n\n"
                            seq = ev_id + 1
                        replayed = True
                if not replayed:
                    yield f": no-backlog-replay-from {last_seen}\n"
            except Exception:
                # If event store fails, continue without replay
                yield f": no-backlog-replay-from {last_seen}\n"

        # Redis or polling stream for live events
        try:
            r = get_redis()
        except Exception:
            r = None

        async def _record_event(ev_id: int, ev_type: str, payload: str):
            try:
                await event_store_impl.append(job_id, SSEEvent(id=ev_id, event_type=ev_type, data=payload))
            except Exception:
                pass  # Best-effort event recording

        async def _emit_terminal_and_end(status_val: str):
            nonlocal seq
            # status event already emitted by caller before invoking this (optional); ensure end event with JSON payload
            end_payload = json.dumps({"job_id": job_id, "final": status_val})
            yield f"id: {seq}\nevent: end\ndata: {end_payload}\n\n"
            await _record_event(seq, "end", end_payload)
            seq += 1

        # Heartbeat interval configurable via settings (default 15s)
        try:
            heartbeat_interval = int(getattr(settings, "JOB_SSE_HEARTBEAT_SECS", 15))
        except Exception:
            heartbeat_interval = 15
        last_hb = time.time()

        # If Redis available, subscribe; else we'll poll
        pub = None
        if r:
            try:
                pub = r.pubsub()
                pub.subscribe(f"jobs:{job_id}")
            except Exception:
                pub = None

        def _maybe_emit_heartbeat():
            nonlocal last_hb
            now = time.time()
            if now - last_hb >= heartbeat_interval:
                last_hb = now
                return f": heartbeat {seq}\n"
            return None

        try:
            while True:
                # Presence backoff: allow slight delay for just-created job to appear
                job_doc = None
                with contextlib.suppress(Exception):
                    job_doc = await job_store_impl.get(job_id)

                if not job_doc:
                    backoff_end = time.time() + 0.2  # 200ms total
                    while time.time() < backoff_end:
                        try:
                            job_doc = await job_store_impl.get(job_id)
                            if job_doc:
                                break
                        except Exception:
                            pass
                        await asyncio.sleep(0.01)

                try:
                    job_doc = await job_store_impl.get(job_id)
                except Exception:
                    job_doc = None

                if not job_doc:
                    err_payload = json.dumps({"error": "job not found"})
                    yield f"id: {seq}\nevent: error\ndata: {err_payload}\n\n"
                    await _record_event(seq, "error", err_payload)
                    seq += 1
                    break

                # If job already terminal before we started streaming and we haven't emitted anything yet (beyond retry / optional replay)
                if job_doc.status.is_terminal and seq == (last_seen + 1 if last_seen else 1) and not replayed:
                    status_payload = json.dumps({"job_id": job_id, "status": job_doc.status.value})
                    yield f"id: {seq}\nevent: status\ndata: {status_payload}\n\n"
                    await _record_event(seq, "status", status_payload)
                    seq += 1
                    async for line in _emit_terminal_and_end(job_doc.status.value):
                        yield line
                    break

                msg = None
                if pub is not None:
                    try:
                        msg = await asyncio.to_thread(pub.get_message, timeout=1)
                    except Exception:
                        msg = None
                if msg and msg.get("type") == "message":
                    data_raw = msg.get("data")
                    if isinstance(data_raw, bytes):
                        try:
                            data_raw = data_raw.decode()
                        except Exception:
                            data_raw = str(data_raw)
                    # Expect JSON string already; don't double encode
                    payload = data_raw
                    yield f"id: {seq}\nevent: message\ndata: {payload}\n\n"
                    await _record_event(seq, "message", payload)
                    seq += 1
                    # If job now terminal, emit final end and exit
                    try:
                        job_doc = await job_store_impl.get(job_id)
                        if job_doc and job_doc.status.is_terminal:
                            term_payload = json.dumps({"job_id": job_id, "status": job_doc.status.value})
                            yield f"id: {seq}\nevent: status\ndata: {term_payload}\n\n"
                            await _record_event(seq, "status", term_payload)
                            seq += 1
                            async for line in _emit_terminal_and_end(job_doc.status.value):
                                yield line
                            break
                    except Exception:
                        pass
                else:
                    # Polling fallback every 0.2s
                    # Re-fetch in case job removed mid-stream
                    job_doc2 = None
                    with contextlib.suppress(Exception):
                        job_doc2 = await job_store_impl.get(job_id)

                    if not job_doc2:
                        # emit terminal end with disappearance notice
                        note_payload = json.dumps({"job_id": job_id, "final": "disappeared"})
                        yield f"id: {seq}\nevent: end\ndata: {note_payload}\n\n"
                        await _record_event(seq, "end", note_payload)
                        seq += 1
                        break
                    job_doc = job_doc2
                    if not job_doc.status.is_terminal:
                        # Heartbeat (only while active)
                        hb_line = _maybe_emit_heartbeat()
                        if hb_line:
                            yield hb_line
                        await asyncio.sleep(0.2)
                    else:
                        # Emit status then end and break
                        status_payload = json.dumps({"job_id": job_id, "status": job_doc.status.value})
                        yield f"id: {seq}\nevent: status\ndata: {status_payload}\n\n"
                        await _record_event(seq, "status", status_payload)
                        seq += 1
                        async for line in _emit_terminal_and_end(job_doc.status.value):
                            yield line
                        break
        except asyncio.CancelledError:
            # Client disconnected; cleanup and exit quietly
            try:
                # log minimal message; provenance/logging omitted for brevity
                pass
            finally:
                if pub is not None:
                    with contextlib.suppress(Exception):
                        pub.close()
            raise
        finally:
            if pub is not None:
                with contextlib.suppress(Exception):
                    pub.close()

    headers = {
        "Cache-Control": "no-store",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
        "Access-Control-Expose-Headers": "X-Request-Id",
        # X-Request-Id is set by middleware (unique per request, not job_id)
    }
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)
