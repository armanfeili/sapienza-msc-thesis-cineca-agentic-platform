"""
Admin-facing proxy for internal DB maintenance endpoints.

These routes mirror the behavior of /internal/db/* but are gated with require_admin
instead of require_internal, allowing platform admins to perform database operations
through the API without needing service tokens.

Storage and logic are shared with the internal endpoints to avoid drift.
"""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Response, status
from pydantic import BaseModel, Field

from db.redis_cache.async_client import get_async_redis
from src.security.admin import require_admin
from src.security.jwt import Principal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["admin-db"])


# ============================================================================
# Shared Models (same as internal_db)
# ============================================================================


class CreateJobRequest(BaseModel):
    """Request to create a database maintenance job."""

    kind: str = Field(..., description="Job type: 'create', 'migrate', 'vacuum', etc.")
    sql: str | None = Field(default=None, description="Optional SQL to execute")
    target: str | None = Field(default=None, description="Target database: 'memgraph', 'postgres'")


class CreateJobResponse(BaseModel):
    """Response from creating a job."""

    ok: bool = True
    job_id: str = Field(..., description="Unique job identifier")


class JobStatusResponse(BaseModel):
    """Status of a database job."""

    job_id: str
    state: str = Field(description="'pending', 'running', 'completed', 'failed', 'cancelled'")
    progress: int = Field(ge=0, le=100, description="Progress percentage")
    created_at: str
    updated_at: str
    error: str | None = None


class CountsResponse(BaseModel):
    """Database node/edge counts."""

    ok: bool = True
    nodes: int = Field(ge=0, description="Total node count")
    edges: int | None = Field(default=None, description="Total edge count (if available)")


# ============================================================================
# Shared Service Functions
# ============================================================================


async def _create_job_in_redis(job_id: str, kind: str, target: str | None) -> None:
    """
    Create job record in Redis.

    Jobs are stored with 24h TTL for idempotency tracking.
    """
    try:
        redis = await get_async_redis()
        job_data = {"job_id": job_id, "kind": kind, "target": target or "unknown", "state": "pending", "progress": 0}

        await redis.setex(f"internal:db:job:{job_id}", 86400, str(job_data))  # 24h TTL

        logger.info(f"Created job {job_id}", extra={"job_id": job_id, "kind": kind})
    except Exception as e:
        logger.warning(f"Failed to create job in Redis: {e}")


async def _get_job_from_redis(job_id: str) -> dict | None:
    """Read job status from Redis."""
    try:
        redis = await get_async_redis()
        raw = await redis.get(f"internal:db:job:{job_id}")
        if raw:
            # TODO: Parse actual job data
            return {
                "job_id": job_id,
                "state": "pending",
                "progress": 0,
                "created_at": "2025-10-22T10:00:00Z",
                "updated_at": "2025-10-22T10:00:00Z",
            }
        return None
    except Exception as e:
        logger.warning(f"Failed to read job from Redis: {e}")
        return None


async def _cancel_job_in_redis(job_id: str) -> None:
    """Mark job as cancelled in Redis."""
    try:
        redis = await get_async_redis()
        await redis.delete(f"internal:db:job:{job_id}")
        logger.info(f"Cancelled job {job_id}", extra={"job_id": job_id})
    except Exception as e:
        logger.warning(f"Failed to cancel job in Redis: {e}")


# ============================================================================
# Admin Routes (Proxy to Internal Logic)
# ============================================================================


@router.post(
    "/jobs",
    response_model=CreateJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create database maintenance job (Admin)",
    description="""
    Admin-facing proxy for internal DB job creation.

    Creates a background database maintenance job (migrate, vacuum, etc.).

    **Access:** Requires `admin:all` scope.

    **Idempotency:** Use `Idempotency-Key` header to prevent duplicate job creation.
    Keys are cached for 24 hours.

    **Mirrors:** `POST /v1/internal/db/jobs`
    """,
    responses={
        202: {
            "description": "Job created (or previously created with same idempotency key)",
            "headers": {"Location": {"description": "URL to check job status", "schema": {"type": "string"}}},
            "content": {
                "application/json": {"example": {"ok": True, "job_id": "550e8400-e29b-41d4-a716-446655440000"}}
            },
        },
        403: {"description": "Forbidden - requires admin:all scope"},
        422: {"description": "Validation error"},
    },
)
async def admin_create_job(
    request: CreateJobRequest,
    response: Response,
    principal: Annotated[Principal, Depends(require_admin())],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> CreateJobResponse:
    """
    Admin endpoint to create database maintenance job.

    Calls the same storage layer as /internal/db/jobs.
    """
    # Check idempotency key
    if idempotency_key:
        try:
            redis = await get_async_redis()
            cached = await redis.get(f"idempotency:db_job:{idempotency_key}")
            if cached:
                logger.info(
                    f"Returning cached job for idempotency key {idempotency_key}",
                    extra={"key": idempotency_key, "actor": principal.sub},
                )
                job_id = cached.decode() if isinstance(cached, bytes) else cached
                response.headers["Location"] = f"/v1/admin/db/jobs/{job_id}"
                return CreateJobResponse(ok=True, job_id=job_id)
        except Exception as e:
            logger.warning(f"Failed to check idempotency key: {e}")

    # Create new job
    job_id = str(uuid.uuid4())

    await _create_job_in_redis(job_id, request.kind, request.target)

    # Cache idempotency key if provided
    if idempotency_key:
        try:
            redis = await get_async_redis()
            await redis.setex(f"idempotency:db_job:{idempotency_key}", 86400, job_id)  # 24h
        except Exception as e:
            logger.warning(f"Failed to cache idempotency key: {e}")

    response.headers["Location"] = f"/v1/admin/db/jobs/{job_id}"

    logger.info(
        f"Created job {job_id} by admin {principal.sub}",
        extra={"actor": principal.sub, "job_id": job_id, "kind": request.kind, "target": request.target},
    )

    return CreateJobResponse(ok=True, job_id=job_id)


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get database job status (Admin)",
    description="""
    Admin-facing proxy for internal job status check.

    Returns the current state and progress of a database maintenance job.

    **Access:** Requires `admin:all` scope.

    **Mirrors:** `GET /v1/internal/db/jobs/{job_id}`
    """,
    responses={
        200: {
            "description": "Job status",
            "content": {
                "application/json": {
                    "example": {
                        "job_id": "550e8400-e29b-41d4-a716-446655440000",
                        "state": "running",
                        "progress": 45,
                        "created_at": "2025-10-22T10:00:00Z",
                        "updated_at": "2025-10-22T10:05:00Z",
                    }
                }
            },
        },
        404: {"description": "Job not found"},
        403: {"description": "Forbidden - requires admin:all scope"},
    },
)
async def admin_get_job_status(
    job_id: Annotated[str, Path(description="Job ID to check")],
    principal: Annotated[Principal, Depends(require_admin())],
) -> JobStatusResponse:
    """
    Admin endpoint to get job status.

    Reads from the same Redis keys as /internal/db/jobs/{job_id}.
    """
    job_data = await _get_job_from_redis(job_id)

    if not job_data:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"type": "about:blank", "title": "Not Found", "status": 404, "detail": f"Job {job_id} not found"},
        )

    logger.info(f"Job status requested by admin {principal.sub}", extra={"actor": principal.sub, "job_id": job_id})

    return JobStatusResponse(**job_data)


@router.delete(
    "/jobs/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cancel database job (Admin)",
    description="""
    Admin-facing proxy for internal job cancellation.

    Cancels a running database maintenance job. This operation is idempotent -
    cancelling an already-cancelled or non-existent job returns 204.

    **Access:** Requires `admin:all` scope.

    **Mirrors:** `DELETE /v1/internal/db/jobs/{job_id}`
    """,
    responses={
        204: {"description": "Job cancelled (or already cancelled/not found)"},
        403: {"description": "Forbidden - requires admin:all scope"},
    },
)
async def admin_cancel_job(
    job_id: Annotated[str, Path(description="Job ID to cancel")],
    principal: Annotated[Principal, Depends(require_admin())],
) -> Response:
    """
    Admin endpoint to cancel job.

    Calls the same storage layer as /internal/db/jobs/{job_id} DELETE.
    """
    await _cancel_job_in_redis(job_id)

    logger.info(f"Job {job_id} cancelled by admin {principal.sub}", extra={"actor": principal.sub, "job_id": job_id})

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/counts",
    response_model=CountsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get database counts (Admin)",
    description="""
    Admin-facing proxy for internal database counts.

    Returns node and edge counts from the graph database (Memgraph).

    **Access:** Requires `admin:all` scope.

    **Mirrors:** `GET /v1/internal/db/counts`
    """,
    responses={
        200: {
            "description": "Database counts",
            "content": {"application/json": {"example": {"ok": True, "nodes": 1234, "edges": 5678}}},
        },
        501: {"description": "Memgraph unavailable or not configured"},
        403: {"description": "Forbidden - requires admin:all scope"},
    },
)
async def admin_get_counts(principal: Annotated[Principal, Depends(require_admin())]) -> CountsResponse:
    """
    Admin endpoint to get database counts.

    Reads from the same Memgraph instance as /internal/db/counts.
    """
    # TODO: Implement actual Memgraph query
    # For now, return placeholder counts

    logger.info(f"Database counts requested by admin {principal.sub}", extra={"actor": principal.sub})

    return CountsResponse(ok=True, nodes=1234, edges=5678)
