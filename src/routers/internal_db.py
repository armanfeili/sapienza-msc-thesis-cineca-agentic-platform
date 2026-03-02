"""
Internal database operations router for platform operators.

All endpoints require internal:all permission (service token or internal claim).
Platform admins (admin:all) cannot bypass this requirement.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from db.postgres_control.database import get_db
from db.postgres_control.models.job import Job
from db.postgres_control.models.job_event import JobEvent
from db.redis_cache.client import cache_get_json, cache_set_json
from src.config import settings
from src.security.internal import require_internal
from src.security.jwt import Principal

logger = logging.getLogger(__name__)

router = APIRouter(tags=["internal"])


# ---------------- Models ----------------
class DBJobRequest(BaseModel):
    """Request to create a database job."""

    type: Literal["create", "populate"] = Field(
        ...,
        description="Job type: 'create' (rebuild DB) or 'populate' (add test data)",
        examples=["create", "populate"],
    )
    wipe: bool | None = Field(
        None, description="For type=create: whether to wipe existing DB first", examples=[True, False]
    )
    users: int | None = Field(
        None, ge=0, description="For type=populate: number of users to generate", examples=[10, 100, 1000]
    )

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"type": "create", "wipe": True}, {"type": "populate", "users": 100}]}
    )


class DBJobResponse(BaseModel):
    """Response from creating a database job."""

    ok: bool
    job_id: str


class DBJobStatusResponse(BaseModel):
    """Response from getting job status."""

    job_id: str
    state: str
    progress: float
    started_at: str | None = None
    finished_at: str | None = None
    message: str | None = None
    action: str
    params: dict[str, Any]


class DBCountsResponse(BaseModel):
    """Response from getting DB counts."""

    ok: bool
    nodes: int
    edges: int | None = None


# ---------------- Helper Functions ----------------
def _get_correlation_id(request: Request, x_correlation_id: str | None = None) -> str:
    """Extract or generate correlation ID for request tracking."""
    return x_correlation_id or str(uuid4())


def _emit_audit_log(
    actor: str,
    action: str,
    resource: str,
    correlation_id: str,
    params: dict,
    result: str,
    duration_ms: float,
) -> None:
    """Emit audit log for internal DB operations."""
    try:
        logger.info(
            "internal_db_audit",
            extra={
                "actor": actor,
                "action": action,
                "resource": resource,
                "correlation_id": correlation_id,
                "params": {k: v for k, v in params.items() if k not in ("token", "authorization")},
                "result": result,
                "duration_ms": duration_ms,
            },
        )
    except Exception as e:
        logger.warning(f"Failed to emit audit log: {e}")


# ---------------- Background Job Runners ----------------
def _run_create_job(job_id: UUID, wipe: bool, users: int | None, db_session_maker):
    """Background task to run create job."""
    db = db_session_maker()

    def progress_callback(progress: float, message: str):
        """Update job progress in Redis and PostgreSQL."""
        try:
            # Store progress in Redis (ephemeral, fast)
            progress_key = f"internal:db:jobs:{job_id}:progress"
            cache_set_json(progress_key, {"progress": progress, "message": message}, ex=3600)

            # Check for cancel signal
            cancel_key = f"internal:db:jobs:{job_id}:cancel"
            if cache_get_json(cancel_key):
                logger.info(f"Job {job_id} cancel signal detected")
                raise RuntimeError("Job cancelled by operator")

            # Log progress
            logger.info(f"Job {job_id} progress: {progress:.1f}% - {message}")

            # Add event to PostgreSQL for audit trail
            if progress < 0:  # Error signal
                db.add(
                    JobEvent(
                        job_id=job_id,
                        event_type="error",
                        event_json={"message": message},
                    )
                )
                db.commit()
            elif progress % 20 == 0 or progress >= 100:  # Log every 20% and completion
                db.add(
                    JobEvent(
                        job_id=job_id,
                        event_type="progress",
                        event_json={"progress": progress, "message": message},
                    )
                )
                db.commit()
        except Exception as e:
            logger.warning(f"Failed to update progress for job {job_id}: {e}")

    try:
        # Update job to running
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            logger.error(f"Job {job_id} not found")
            return

        job.status = "running"
        job.started_at = datetime.now(UTC)
        db.add(
            JobEvent(
                job_id=job_id,
                event_type="status",
                event_json={"status": "running", "message": "Job started"},
            )
        )
        db.commit()

        logger.info(f"Starting create job {job_id}: wipe={wipe}, users={users}")

        # Check if DB utilities available
        try:
            from db.populate import create_from_original_and_populate
        except ImportError as e:
            logger.error(f"DB utilities unavailable for job {job_id}: {e}")
            job.status = "failed"
            job.completed_at = datetime.now(UTC)
            job.error_json = {"error": "DB utilities unavailable in this runtime image"}
            db.add(
                JobEvent(
                    job_id=job_id,
                    event_type="status",
                    event_json={"status": "failed", "error": "DB utilities unavailable"},
                )
            )
            db.commit()
            return

        # Run the create job with progress tracking
        try:
            result = create_from_original_and_populate(
                wipe=wipe,
                users=users,
                progress_callback=progress_callback,
            )

            logger.info(f"Create job {job_id} completed successfully: {result}")

            job.status = "finished"
            job.completed_at = datetime.now(UTC)
            job.result_json = {"success": True, "wipe": wipe, "users": users, **result}
            db.add(
                JobEvent(
                    job_id=job_id,
                    event_type="status",
                    event_json={"status": "finished", "message": "Job completed successfully", "result": result},
                )
            )
            db.commit()

        except RuntimeError as e:
            if "cancelled" in str(e).lower():
                logger.info(f"Create job {job_id} cancelled")
                job.status = "cancelled"
                job.completed_at = datetime.now(UTC)
                job.error_json = {"error": "Job cancelled by operator"}
                db.add(
                    JobEvent(
                        job_id=job_id,
                        event_type="status",
                        event_json={"status": "cancelled", "message": str(e)},
                    )
                )
                db.commit()
            else:
                raise
        except Exception as e:
            logger.error(f"Create job {job_id} failed: {e}", exc_info=True)
            job.status = "failed"
            job.completed_at = datetime.now(UTC)
            job.error_json = {"error": str(e)}
            db.add(
                JobEvent(
                    job_id=job_id,
                    event_type="status",
                    event_json={"status": "failed", "error": str(e)},
                )
            )
            db.commit()

    except Exception as e:
        logger.error(f"Unexpected error in create job {job_id}: {e}", exc_info=True)
    finally:
        db.close()


def _run_populate_job(job_id: UUID, users: int | None, db_session_maker):
    """Background task to run populate job."""
    db = db_session_maker()

    def progress_callback(progress: float, message: str):
        """Update job progress in Redis and PostgreSQL."""
        try:
            # Store progress in Redis (ephemeral, fast)
            progress_key = f"internal:db:jobs:{job_id}:progress"
            cache_set_json(progress_key, {"progress": progress, "message": message}, ex=3600)

            # Check for cancel signal
            cancel_key = f"internal:db:jobs:{job_id}:cancel"
            if cache_get_json(cancel_key):
                logger.info(f"Job {job_id} cancel signal detected")
                raise RuntimeError("Job cancelled by operator")

            # Log progress
            logger.info(f"Job {job_id} progress: {progress:.1f}% - {message}")

            # Add event to PostgreSQL for audit trail
            if progress < 0:  # Error signal
                db.add(
                    JobEvent(
                        job_id=job_id,
                        event_type="error",
                        event_json={"message": message},
                    )
                )
                db.commit()
            elif progress % 20 == 0 or progress >= 100:  # Log every 20% and completion
                db.add(
                    JobEvent(
                        job_id=job_id,
                        event_type="progress",
                        event_json={"progress": progress, "message": message},
                    )
                )
                db.commit()
        except Exception as e:
            logger.warning(f"Failed to update progress for job {job_id}: {e}")

    try:
        # Update job to running
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            logger.error(f"Job {job_id} not found")
            return

        job.status = "running"
        job.started_at = datetime.now(UTC)
        db.add(
            JobEvent(
                job_id=job_id,
                event_type="status",
                event_json={"status": "running", "message": "Job started"},
            )
        )
        db.commit()

        logger.info(f"Starting populate job {job_id}: users={users}")

        # Check if DB utilities available
        try:
            from db.populate import build_graph, persist_graph
        except ImportError as e:
            logger.error(f"DB utilities unavailable for job {job_id}: {e}")
            job.status = "failed"
            job.completed_at = datetime.now(UTC)
            job.error_json = {"error": "DB utilities unavailable in this runtime image"}
            db.add(
                JobEvent(
                    job_id=job_id,
                    event_type="status",
                    event_json={"status": "failed", "error": "DB utilities unavailable"},
                )
            )
            db.commit()
            return

        # Run the populate job with progress tracking
        try:
            # Build graph (50% of work)
            graph = build_graph(num_users=users or 50, progress_callback=lambda p, m: progress_callback(p * 0.5, m))

            # Persist graph (remaining 50%)
            persist_graph(graph, progress_callback=lambda p, m: progress_callback(50 + p * 0.5, m))

            logger.info(f"Populate job {job_id} completed successfully")

            job.status = "finished"
            job.completed_at = datetime.now(UTC)
            job.result_json = {
                "success": True,
                "users": users,
                "nodes": len(graph.get("nodes", [])),
                "edges": len(graph.get("edges", [])),
            }
            db.add(
                JobEvent(
                    job_id=job_id,
                    event_type="status",
                    event_json={
                        "status": "finished",
                        "message": "Job completed successfully",
                        "result": job.result_json,
                    },
                )
            )
            db.commit()

        except RuntimeError as e:
            if "cancelled" in str(e).lower():
                logger.info(f"Populate job {job_id} cancelled")
                job.status = "cancelled"
                job.completed_at = datetime.now(UTC)
                job.error_json = {"error": "Job cancelled by operator"}
                db.add(
                    JobEvent(
                        job_id=job_id,
                        event_type="status",
                        event_json={"status": "cancelled", "message": str(e)},
                    )
                )
                db.commit()
            else:
                raise
        except Exception as e:
            logger.error(f"Populate job {job_id} failed: {e}", exc_info=True)
            job.status = "failed"
            job.completed_at = datetime.now(UTC)
            job.error_json = {"error": str(e)}
            db.add(
                JobEvent(
                    job_id=job_id,
                    event_type="status",
                    event_json={"status": "failed", "error": str(e)},
                )
            )
            db.commit()

    except Exception as e:
        logger.error(f"Unexpected error in populate job {job_id}: {e}", exc_info=True)
    finally:
        db.close()


# ---------------- Endpoints ----------------
@router.post(
    "/jobs",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=DBJobResponse,
    summary="Create DB job (internal only)",
    description="""
Create a database maintenance job (create or populate). Internal only, requires service token.

**Job Types:**
- `create`: Wipes and recreates database from scratch with optional user count
- `populate`: Generates synthetic data with specified number of users

**Idempotency:**
- Optional `Idempotency-Key` header prevents duplicate job creation
- Replayed requests return existing job with `X-Idempotency-Replayed: true` header
- Idempotency keys expire after 24 hours

**Response Codes:**
- `202 Accepted`: Job queued successfully, poll `/jobs/{job_id}` for status
- `501 Not Implemented`: DB utilities unavailable (check INTERNAL_DB_UTILS_ENABLED)
- `403 Forbidden`: Non-M2M token used
- `500 Internal Server Error`: Unexpected failure

**Headers:**
- `Location`: URL to poll for job status
- `X-Correlation-Id`: Request correlation ID for distributed tracing
""",
    responses={
        202: {
            "description": "Job queued successfully",
            "content": {
                "application/json": {"example": {"ok": True, "job_id": "550e8400-e29b-41d4-a716-446655440000"}}
            },
            "headers": {
                "Location": {"description": "URL to poll for job status", "schema": {"type": "string"}},
                "X-Correlation-Id": {"description": "Request correlation ID", "schema": {"type": "string"}},
                "X-Idempotency-Replayed": {
                    "description": "Present with value 'true' if request was replayed from idempotency key",
                    "schema": {"type": "string"},
                },
            },
        },
        501: {
            "description": "DB utilities unavailable (feature disabled or missing runtime dependencies)",
            "content": {
                "application/json": {
                    "example": {
                        "type": "about:blank",
                        "title": "Not Implemented",
                        "status": 501,
                        "detail": "DB utilities unavailable in this runtime image",
                        "instance": "/v1/internal/db/jobs",
                        "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
                    }
                }
            },
        },
    },
)
async def create_db_job(
    req: DBJobRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user: Principal = Depends(require_internal()),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    x_correlation_id: str | None = Header(None),
) -> Response:
    """Create a database job (create|populate) - internal only."""
    start_time = time.time()
    correlation_id = _get_correlation_id(request, x_correlation_id)

    # Check feature flag first
    if not settings.INTERNAL_DB_UTILS_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={
                "type": "about:blank",
                "title": "Not Implemented",
                "status": 501,
                "detail": "DB utilities unavailable in this runtime image",
                "instance": str(request.url),
                "correlation_id": correlation_id,
            },
        )

    # Validate job type
    if req.type not in ("create", "populate"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "type": "about:blank",
                "title": "Bad Request",
                "status": 400,
                "detail": f"Invalid type: {req.type}. Must be 'create' or 'populate'",
                "instance": str(request.url),
                "correlation_id": correlation_id,
            },
        )

    try:
        # Check for idempotency
        if idempotency_key:
            redis_key = f"internal:db:jobs:idempotency:{idempotency_key}"
            existing_job_id = cache_get_json(redis_key)
            if existing_job_id:
                logger.info(f"Returning existing job {existing_job_id} for idempotency key {idempotency_key}")
                location = f"/v1/internal/db/jobs/{existing_job_id}"
                response = JSONResponse(
                    status_code=status.HTTP_202_ACCEPTED,
                    content={"ok": True, "job_id": existing_job_id},
                    headers={
                        "Location": location,
                        "X-Request-Id": correlation_id,
                        "X-Correlation-Id": correlation_id,
                        "X-Idempotency-Replayed": "true",
                    },
                )
                return response

        # Check runtime capability
        if req.type == "create":
            try:
                from db.populate import create_from_original_and_populate
            except ImportError:
                raise HTTPException(
                    status_code=status.HTTP_501_NOT_IMPLEMENTED,
                    detail={
                        "type": "about:blank",
                        "title": "Not Implemented",
                        "status": 501,
                        "detail": "DB utilities unavailable in this runtime image",
                        "instance": str(request.url),
                        "correlation_id": correlation_id,
                    },
                    headers={"Warning": '299 - "DB utilities not available in this image"'},
                )

        elif req.type == "populate":
            try:
                from db.populate import build_graph, persist_graph
            except ImportError:
                raise HTTPException(
                    status_code=status.HTTP_501_NOT_IMPLEMENTED,
                    detail={
                        "type": "about:blank",
                        "title": "Not Implemented",
                        "status": 501,
                        "detail": "DB utilities unavailable in this runtime image",
                        "instance": str(request.url),
                        "correlation_id": correlation_id,
                    },
                    headers={
                        "Warning": '299 - "DB utilities not available in this image"',
                        "Deprecation": "true",
                        "Link": '<https://docs.example.com/db-populate>; rel="deprecation"',
                    },
                )

        # Create job in PostgreSQL
        job = Job(
            type=f"internal.db.{req.type}",
            status="queued",
            owner_sub=user.sub,
            tenant_id=None,  # Internal M2M jobs have no tenant (global scope)
            payload_json=req.model_dump(),
            idempotency_key=idempotency_key,
        )
        db.add(job)
        db.flush()

        job_id = job.id

        # Add initial event
        db.add(
            JobEvent(
                job_id=job_id,
                event_type="status",
                event_json={"status": "queued", "message": "Job queued"},
            )
        )
        db.commit()

        # Store idempotency mapping in Redis (24h)
        if idempotency_key:
            redis_key = f"internal:db:jobs:idempotency:{idempotency_key}"
            cache_set_json(redis_key, str(job_id), ex=24 * 3600)

        # Queue background task
        from db.postgres_control.database import SessionLocal

        if req.type == "create":
            background_tasks.add_task(
                _run_create_job,
                job_id,
                req.wipe if req.wipe is not None else True,
                req.users,
                SessionLocal,
            )
        else:
            background_tasks.add_task(
                _run_populate_job,
                job_id,
                req.users,
                SessionLocal,
            )

        duration_ms = (time.time() - start_time) * 1000
        _emit_audit_log(
            actor=user.sub,
            action="create_db_job",
            resource="/v1/internal/db/jobs",
            correlation_id=correlation_id,
            params={"type": req.type, "wipe": req.wipe, "users": req.users},
            result="success",
            duration_ms=duration_ms,
        )

        location = f"/v1/internal/db/jobs/{job_id}"
        response = JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"ok": True, "job_id": str(job_id)},
            headers={
                "Location": location,
                "X-Request-Id": correlation_id,
                "X-Correlation-Id": correlation_id,
            },
        )
        return response

    except HTTPException:
        raise
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error(f"Failed to create DB job: {e}", exc_info=True)
        _emit_audit_log(
            actor=user.sub,
            action="create_db_job",
            resource="/v1/internal/db/jobs",
            correlation_id=correlation_id,
            params={"type": req.type},
            result="error",
            duration_ms=duration_ms,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "type": "about:blank",
                "title": "Internal Server Error",
                "status": 500,
                "detail": "Failed to create DB job",
                "instance": str(request.url),
                "correlation_id": correlation_id,
            },
        )


@router.get(
    "/jobs/{job_id}",
    response_model=DBJobStatusResponse,
    summary="Get DB job status (internal only)",
    description="""
Retrieve database job status by ID. Internal only, requires service token.

**Job States:**
- `queued`: Job created but not yet started
- `running`: Job currently executing
- `finished`: Job completed successfully
- `failed`: Job encountered an error
- `cancelled`: Job was cancelled by operator

**Progress Tracking:**
- Real-time progress (0.0-1.0) from Redis for running jobs
- Includes human-readable progress message when available
- Progress is 0.0 for failed/cancelled jobs, 1.0 for finished

**Polling Recommendation:**
- Poll every 2-5 seconds for running jobs
- Stop polling when state is finished/failed/cancelled
""",
    responses={
        200: {
            "description": "Job status retrieved",
            "content": {
                "application/json": {
                    "example": {
                        "job_id": "550e8400-e29b-41d4-a716-446655440000",
                        "state": "running",
                        "progress": 0.65,
                        "message": "Persisting graph data: 65/100 batches",
                        "started_at": "2025-01-15T10:30:00Z",
                        "finished_at": None,
                        "action": "populate",
                        "params": {"type": "populate", "users": 100, "wipe": False},
                    }
                }
            },
        },
        404: {
            "description": "Job not found",
            "content": {
                "application/json": {
                    "example": {
                        "type": "about:blank",
                        "title": "Not Found",
                        "status": 404,
                        "detail": "Job not found: 550e8400-e29b-41d4-a716-446655440000",
                        "instance": "/v1/internal/db/jobs/550e8400-e29b-41d4-a716-446655440000",
                        "correlation_id": "650e8400-e29b-41d4-a716-446655440000",
                    }
                }
            },
        },
    },
)
async def get_db_job(
    job_id: str,
    request: Request,
    user: Principal = Depends(require_internal()),
    db: Session = Depends(get_db),
    x_correlation_id: str | None = Header(None),
) -> DBJobStatusResponse:
    """Get database job status - internal only."""
    start_time = time.time()
    correlation_id = _get_correlation_id(request, x_correlation_id)

    try:
        # Query job from PostgreSQL
        try:
            job_uuid = UUID(job_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "type": "about:blank",
                    "title": "Not Found",
                    "status": 404,
                    "detail": f"Job not found: {job_id}",
                    "instance": str(request.url),
                    "correlation_id": correlation_id,
                },
            )

        job = db.query(Job).filter(Job.id == job_uuid).first()
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "type": "about:blank",
                    "title": "Not Found",
                    "status": 404,
                    "detail": f"Job not found: {job_id}",
                    "instance": str(request.url),
                    "correlation_id": correlation_id,
                },
            )

        # Calculate progress from Redis (real-time) or PostgreSQL (fallback)
        progress = 0.0
        progress_message = None

        if job.status == "running":
            # Try to get real-time progress from Redis
            progress_key = f"internal:db:jobs:{job_id}:progress"
            progress_data = cache_get_json(progress_key)

            if progress_data:
                progress = progress_data.get("progress", 0.0) / 100.0  # Convert 0-100 to 0-1
                progress_message = progress_data.get("message")
            else:
                # Fallback: estimate 50% if running but no Redis data
                progress = 0.5
        elif job.status == "finished":
            progress = 1.0
        elif job.status in ["failed", "cancelled"]:
            progress = 0.0  # Don't show progress for failed/cancelled jobs

        duration_ms = (time.time() - start_time) * 1000
        _emit_audit_log(
            actor=user.sub,
            action="get_db_job",
            resource=f"/v1/internal/db/jobs/{job_id}",
            correlation_id=correlation_id,
            params={"job_id": job_id},
            result="success",
            duration_ms=duration_ms,
        )

        return DBJobStatusResponse(
            job_id=str(job.id),
            state=job.status,
            progress=progress,
            started_at=job.started_at.isoformat() if job.started_at else None,
            finished_at=job.completed_at.isoformat() if job.completed_at else None,
            message=progress_message or (job.error_json.get("error") if job.error_json else None),
            action=job.type.replace("internal.db.", ""),
            params=job.payload_json or {},
        )

    except HTTPException:
        raise
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error(f"Failed to get DB job status: {e}", exc_info=True)
        _emit_audit_log(
            actor=user.sub,
            action="get_db_job",
            resource=f"/v1/internal/db/jobs/{job_id}",
            correlation_id=correlation_id,
            params={"job_id": job_id},
            result="error",
            duration_ms=duration_ms,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "type": "about:blank",
                "title": "Internal Server Error",
                "status": 500,
                "detail": "Failed to retrieve job status",
                "instance": str(request.url),
                "correlation_id": correlation_id,
            },
        )


@router.delete(
    "/jobs/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cancel DB job (internal only)",
    description="""
Cancel a database job. Idempotent - returns 204 whether job was canceled, already finished, or not found.

**Cancellation Behavior:**
- Sets cancel flag in Redis (5-minute TTL)
- Running jobs check flag periodically and stop gracefully
- Already-finished jobs: no-op, returns 204
- Non-existent jobs: no-op, returns 204 (idempotent)

**Idempotency:**
- Always returns 204 No Content
- Safe to call multiple times
- No error if job doesn't exist

**Use Cases:**
- Stop long-running populate job
- Abort create job before completion
- Clean up stuck jobs
""",
    responses={204: {"description": "Job cancel signal sent (or job already finished/not found)"}},
)
async def cancel_db_job(
    job_id: str,
    request: Request,
    user: Principal = Depends(require_internal()),
    db: Session = Depends(get_db),
    x_correlation_id: str | None = Header(None),
) -> Response:
    """Cancel a database job - internal only, idempotent."""
    start_time = time.time()
    correlation_id = _get_correlation_id(request, x_correlation_id)

    try:
        # Try to parse job ID
        try:
            job_uuid = UUID(job_id)
        except ValueError:
            # Invalid UUID - return 204 (idempotent)
            duration_ms = (time.time() - start_time) * 1000
            _emit_audit_log(
                actor=user.sub,
                action="cancel_db_job",
                resource=f"/v1/internal/db/jobs/{job_id}",
                correlation_id=correlation_id,
                params={"job_id": job_id},
                result="not_found_idempotent",
                duration_ms=duration_ms,
            )
            response = Response(status_code=status.HTTP_204_NO_CONTENT)
            response.headers["X-Request-Id"] = correlation_id
            response.headers["X-Correlation-Id"] = correlation_id
            return response

        # Try to find job
        job = db.query(Job).filter(Job.id == job_uuid).first()

        if not job:
            # Job not found - return 204 (idempotent)
            duration_ms = (time.time() - start_time) * 1000
            _emit_audit_log(
                actor=user.sub,
                action="cancel_db_job",
                resource=f"/v1/internal/db/jobs/{job_id}",
                correlation_id=correlation_id,
                params={"job_id": job_id},
                result="not_found_idempotent",
                duration_ms=duration_ms,
            )
            response = Response(status_code=status.HTTP_204_NO_CONTENT)
            response.headers["X-Request-Id"] = correlation_id
            response.headers["X-Correlation-Id"] = correlation_id
            return response

        # If already terminal, return 204 (idempotent)
        if job.status in ("finished", "failed", "cancelled"):
            duration_ms = (time.time() - start_time) * 1000
            _emit_audit_log(
                actor=user.sub,
                action="cancel_db_job",
                resource=f"/v1/internal/db/jobs/{job_id}",
                correlation_id=correlation_id,
                params={"job_id": job_id, "prior_status": job.status},
                result="already_terminal_idempotent",
                duration_ms=duration_ms,
            )
            response = Response(status_code=status.HTTP_204_NO_CONTENT)
            response.headers["X-Request-Id"] = correlation_id
            response.headers["X-Correlation-Id"] = correlation_id
            return response

        # Set cancel signal in Redis (runner should check this)
        cancel_key = f"internal:db:jobs:{job_id}:cancel"
        cache_set_json(cancel_key, True, ex=300)  # 5 min TTL

        # Update job status to cancelled
        job.status = "cancelled"
        job.completed_at = datetime.now(UTC)
        job.error_json = {"message": "Cancel requested"}
        db.add(
            JobEvent(
                job_id=job_uuid,
                event_type="status",
                event_json={"status": "cancelled", "message": "Cancel requested by operator"},
            )
        )
        db.commit()

        duration_ms = (time.time() - start_time) * 1000
        _emit_audit_log(
            actor=user.sub,
            action="cancel_db_job",
            resource=f"/v1/internal/db/jobs/{job_id}",
            correlation_id=correlation_id,
            params={"job_id": job_id},
            result="cancelled",
            duration_ms=duration_ms,
        )

        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        response.headers["X-Request-Id"] = correlation_id
        response.headers["X-Correlation-Id"] = correlation_id
        return response

    except HTTPException:
        raise
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error(f"Failed to cancel DB job: {e}", exc_info=True)
        _emit_audit_log(
            actor=user.sub,
            action="cancel_db_job",
            resource=f"/v1/internal/db/jobs/{job_id}",
            correlation_id=correlation_id,
            params={"job_id": job_id},
            result="error",
            duration_ms=duration_ms,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "type": "about:blank",
                "title": "Internal Server Error",
                "status": 500,
                "detail": "Failed to cancel job",
                "instance": str(request.url),
                "correlation_id": correlation_id,
            },
        )


@router.get(
    "/counts",
    response_model=DBCountsResponse,
    summary="Get DB node count (internal only)",
    description="Get count of nodes and edges in graph database. Internal only, requires service token.",
)
async def get_db_counts(
    request: Request,
    user: Principal = Depends(require_internal()),
    x_correlation_id: str | None = Header(None),
) -> DBCountsResponse:
    """Get database node/edge counts - internal only."""
    start_time = time.time()
    correlation_id = _get_correlation_id(request, x_correlation_id)

    try:
        # Check if Memgraph client available
        feature_available = True
        try:
            from db.memgraph_domain import memgraph_client
        except ImportError:
            feature_available = False

        # Check if feature is enabled
        if hasattr(settings, "FEATURE_MEMGRAPH_COUNTS"):
            if not settings.FEATURE_MEMGRAPH_COUNTS:
                feature_available = False

        if not feature_available:
            # Return 501 with helpful headers
            response = JSONResponse(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                content={
                    "type": "about:blank",
                    "title": "Not Implemented",
                    "status": 501,
                    "detail": "Memgraph counts unavailable: feature disabled or client not available",
                    "instance": str(request.url),
                    "extensions": {
                        "correlation_id": correlation_id,
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                },
                headers={
                    "Retry-After": "60",
                    "X-Feature": "memgraph=unavailable",
                    "X-Request-Id": correlation_id,
                    "X-Correlation-Id": correlation_id,
                },
            )

            duration_ms = (time.time() - start_time) * 1000
            _emit_audit_log(
                actor=user.sub,
                action="get_db_counts",
                resource="/v1/internal/db/counts",
                correlation_id=correlation_id,
                params={},
                result="feature_unavailable",
                duration_ms=duration_ms,
            )

            return response

        # Query counts
        try:
            mg = memgraph_client.get_memgraph()

            # Count nodes
            node_res = list(mg.execute_and_fetch("MATCH (n) RETURN count(n) AS c"))
            node_count = int(node_res[0]["c"]) if node_res else 0

            # Count edges
            edge_res = list(mg.execute_and_fetch("MATCH ()-[r]->() RETURN count(r) AS c"))
            edge_count = int(edge_res[0]["c"]) if edge_res else 0

            duration_ms = (time.time() - start_time) * 1000
            _emit_audit_log(
                actor=user.sub,
                action="get_db_counts",
                resource="/v1/internal/db/counts",
                correlation_id=correlation_id,
                params={},
                result="success",
                duration_ms=duration_ms,
            )

            return DBCountsResponse(
                ok=True,
                nodes=node_count,
                edges=edge_count,
            )

        except Exception as e:
            logger.error(f"Memgraph query failed: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "type": "about:blank",
                    "title": "Internal Server Error",
                    "status": 500,
                    "detail": f"Database query failed: {e!s}",
                    "instance": str(request.url),
                    "correlation_id": correlation_id,
                },
            )

    except HTTPException:
        raise
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error(f"Failed to get DB counts: {e}", exc_info=True)
        _emit_audit_log(
            actor=user.sub,
            action="get_db_counts",
            resource="/v1/internal/db/counts",
            correlation_id=correlation_id,
            params={},
            result="error",
            duration_ms=duration_ms,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "type": "about:blank",
                "title": "Internal Server Error",
                "status": 500,
                "detail": "Failed to get database counts",
                "instance": str(request.url),
                "correlation_id": correlation_id,
            },
        )
