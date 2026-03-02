"""
Router exposing lightweight process management for built-in models started by the app.

All endpoints require admin:all permission and implement proper RBAC, observability,
idempotency, and error handling according to RFC 7807 (Problem Details for HTTP APIs).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from db.postgres_control.database import get_db
from db.postgres_control.models.builtin_process import ManifestStatus, ProcessEvent
from src.models.process_models import (
    ManifestHistoryResponse,
    ProcessHistoryResponse,
    ProcessListResponse,
)
from src.security.admin import require_admin
from src.security.jwt import Principal
from src.services.process_service import (
    get_manifest_history,
    get_process_history,
    list_processes,
    stop_process,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-processes"])


def _get_correlation_id(request: Request, x_correlation_id: str | None = Header(None)) -> str:
    """Extract or generate correlation ID for request tracking."""
    return x_correlation_id or str(uuid4())


def _add_observability_headers(response: Response, correlation_id: str) -> None:
    """Add observability headers to response."""
    response.headers["X-Request-Id"] = correlation_id
    response.headers["X-Trace-Id"] = correlation_id


def _emit_audit_log(
    actor: str,
    action: str,
    resource: str,
    correlation_id: str,
    params: dict,
    result: str,
    duration_ms: float,
) -> None:
    """Emit audit log for admin operations."""
    try:
        # Use structured logging
        logger.info(
            "admin_processes_audit",
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


def _emit_metric(metric_name: str, value: float, tags: dict) -> None:
    """Emit metric for observability."""
    try:
        # Placeholder for metrics system (e.g., StatsD, Prometheus)
        logger.debug(f"metric: {metric_name}={value} tags={tags}")
    except Exception:
        pass


# ---------------- Endpoints ----------------
@router.get(
    "",
    response_model=ProcessListResponse,
    summary="List active and recent built-in processes",
    description="""
GET /v1/admin/processes – View all running and recent model processes

**Why we need this endpoint:**
- Administrators need visibility into which AI models are currently running on the platform
- Essential for monitoring system resources and identifying stuck or stale processes
- Helps troubleshoot issues by seeing which models were recently active
- Without this, admins have no way to see what's happening on the system in real-time

**What it does:**
- Shows all currently running built-in model processes (e.g., LLaMA, Whisper, embeddings)
- Displays recently stopped processes for audit purposes
- Merges live data from Redis with historical records from PostgreSQL
- Provides filtering by artifact name, status, tenant, and time range
- Returns process details including PID, port, status, and last heartbeat

**Access:**
- Admin only – requires `admin:all` permission
- Returns 401 for missing/invalid tokens
- Returns 403 for non-admin users

**Behavior:**
- **Data source**: Combines Redis runtime state + PostgreSQL audit logs
- **Sorting**: Active processes first, then by timestamp (newest first)
- **Pagination**: Default 100 results, max 1000 per request
- **Filters available**:
  - `artifact`: Model name (e.g., "llama3-8b")
  - `status`: Process status (running, starting, stopping, exited, stale)
  - `since`: ISO 8601 timestamp to see events after a specific time
  - `tenant_id`: Filter by tenant
  - `limit`: Number of results (1-1000)

**Responses:**
- 200: OK – Successfully retrieved process list with process details
- 401: Unauthorized – Missing or invalid authentication token
- 403: Forbidden – User lacks admin:all permission
- 500: Internal Server Error – Database or Redis connection issue

**Examples:**
```bash
# List all active processes
curl -X GET "http://localhost:8000/v1/admin/processes" \\
     -H "Authorization: Bearer $ADMIN_TOKEN"

# Filter by artifact and status
curl -X GET "http://localhost:8000/v1/admin/processes?artifact=llama3-8b&status=running&limit=50" \\
     -H "Authorization: Bearer $ADMIN_TOKEN"

# Get processes for specific tenant
curl -X GET "http://localhost:8000/v1/admin/processes?tenant_id=acme-corp" \\
     -H "Authorization: Bearer $ADMIN_TOKEN"
```
    """,
    responses={
        200: {
            "description": "Process list retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "processes": [
                            {
                                "id": "llama3-8b-1234",
                                "process_id": "builtin:llama3-8b:abc123",
                                "artifact": "llama3-8b",
                                "pid": 42789,
                                "port": 8080,
                                "status": "running",
                                "ts": "2025-10-21T10:30:00Z",
                                "tenant_id": None,
                                "manifest_version": "v1.2.3",
                                "host": "localhost",
                                "last_heartbeat": "2025-10-21T10:35:00Z",
                            }
                        ],
                        "next_cursor": None,
                    }
                }
            },
        },
        401: {"description": "Unauthorized - invalid or missing token"},
        403: {"description": "Forbidden - requires admin:all permission"},
        500: {"description": "Internal server error"},
    },
)
async def list_processes_endpoint(
    request: Request,
    user: Principal = Depends(require_admin()),
    db: Session = Depends(get_db),
    artifact: str | None = Query(None, description="Filter by artifact name"),
    process_status: str | None = Query(None, alias="status", description="Filter by status"),
    since: datetime | None = Query(None, description="Filter events after this ISO 8601 timestamp"),
    tenant_id: str | None = Query(None, description="Filter by tenant ID"),
    limit: int = Query(100, ge=1, le=1000, description="Max results to return"),
    x_correlation_id: str | None = Header(None),
) -> ProcessListResponse:
    """List active and recent built-in processes."""
    start_time = time.time()
    correlation_id = _get_correlation_id(request, x_correlation_id)

    try:
        processes, next_cursor = list_processes(
            db=db,
            limit=limit,
            artifact=artifact,
            status=process_status,
            since=since,
            tenant_id=tenant_id,
        )

        duration_ms = (time.time() - start_time) * 1000
        _emit_audit_log(
            actor=user.sub,
            action="list_processes",
            resource="/v1/admin/processes",
            correlation_id=correlation_id,
            params={"artifact": artifact, "status": process_status, "limit": limit},
            result="success",
            duration_ms=duration_ms,
        )
        _emit_metric("admin_processes.list.duration_ms", duration_ms, {"status": "success"})

        return ProcessListResponse(processes=processes, next_cursor=next_cursor)

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error(f"Failed to list processes: {e}", exc_info=True)
        _emit_audit_log(
            actor=user.sub,
            action="list_processes",
            resource="/v1/admin/processes",
            correlation_id=correlation_id,
            params={"artifact": artifact, "status": process_status, "limit": limit},
            result="error",
            duration_ms=duration_ms,
        )
        _emit_metric("admin_processes.list.duration_ms", duration_ms, {"status": "error"})

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "type": "about:blank",
                "title": "Internal Server Error",
                "status": 500,
                "detail": "Failed to retrieve process list",
                "instance": str(request.url),
                "correlation_id": correlation_id,
            },
        )


@router.delete(
    "/{pid}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Stop a built-in process by PID",
    description="""
DELETE /v1/admin/processes/{pid} – Stop a running model process

**Why we need this endpoint:**
- Admins need ability to safely shut down misbehaving or stuck model processes
- Critical for resource management when a model is consuming too much memory or CPU
- Enables graceful cleanup before platform maintenance or restarts
- Without this, admins would have no way to stop runaway processes without killing the entire platform

**What it does:**
- Gracefully stops a built-in model process using its operating system PID (process ID)
- Sends shutdown signal to the process via the runtime adapter
- Removes the process metadata from Redis cache
- Records a stop event in PostgreSQL for audit trail
- Works even if the process is already stopped or never existed (idempotent)

**Access:**
- Admin only – requires `admin:all` permission
- Returns 401 for missing/invalid tokens
- Returns 403 for non-admin users

**Behavior:**
- **Idempotency**: Multiple DELETE calls to the same PID always return 204
- **Concurrency safe**: Uses Redis stop-lock (30 second TTL) to prevent race conditions
- **Always succeeds**: Returns 204 whether process was stopped now, already stopped, or never existed
- **Graceful shutdown**: Attempts to unload process cleanly before terminating

**Responses:**
- 204: No Content – Process stopped successfully (or was already stopped/nonexistent)
- 401: Unauthorized – Missing or invalid authentication token
- 403: Forbidden – User lacks admin:all permission
- 422: Unprocessable Entity – Invalid PID format (must be positive integer)
- 500: Internal Server Error – Failed to communicate with Redis or database

**Examples:**
```bash
# Stop a process by PID
curl -X DELETE "http://localhost:8000/v1/admin/processes/42789" \\
     -H "Authorization: Bearer $ADMIN_TOKEN"

# Stop with correlation ID for tracking
curl -X DELETE "http://localhost:8000/v1/admin/processes/42789" \\
     -H "Authorization: Bearer $ADMIN_TOKEN" \\
     -H "X-Correlation-Id: debug-12345"
```
    """,
    responses={
        204: {"description": "Process stopped successfully or already gone"},
        401: {"description": "Unauthorized - invalid or missing token"},
        403: {"description": "Forbidden - requires admin:all permission"},
        422: {"description": "Unprocessable Entity - invalid PID format"},
        500: {"description": "Internal server error"},
    },
)
async def stop_process_endpoint(
    pid: int,
    request: Request,
    user: Principal = Depends(require_admin()),
    db: Session = Depends(get_db),
    x_correlation_id: str | None = Header(None),
) -> Response:
    """Stop a builtin process by PID (idempotent)."""
    start_time = time.time()
    correlation_id = _get_correlation_id(request, x_correlation_id)

    # Validate PID
    if pid <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "type": "about:blank",
                "title": "Unprocessable Entity",
                "status": 422,
                "detail": f"Invalid PID: {pid}. Must be a positive integer.",
                "instance": str(request.url),
                "correlation_id": correlation_id,
            },
        )

    try:
        stop_process(db=db, pid=pid, actor=user.sub)

        duration_ms = (time.time() - start_time) * 1000
        _emit_audit_log(
            actor=user.sub,
            action="stop_process",
            resource=f"/v1/admin/processes/{pid}",
            correlation_id=correlation_id,
            params={"pid": pid},
            result="success",
            duration_ms=duration_ms,
        )
        _emit_metric("admin_processes.stop.duration_ms", duration_ms, {"status": "success"})

        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        _add_observability_headers(response, correlation_id)
        return response

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error(f"Failed to stop process {pid}: {e}", exc_info=True)
        _emit_audit_log(
            actor=user.sub,
            action="stop_process",
            resource=f"/v1/admin/processes/{pid}",
            correlation_id=correlation_id,
            params={"pid": pid},
            result="error",
            duration_ms=duration_ms,
        )
        _emit_metric("admin_processes.stop.duration_ms", duration_ms, {"status": "error"})

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "type": "about:blank",
                "title": "Internal Server Error",
                "status": 500,
                "detail": f"Failed to stop process {pid}",
                "instance": str(request.url),
                "correlation_id": correlation_id,
            },
        )


@router.get(
    "/history/manifests",
    response_model=ManifestHistoryResponse,
    summary="Get manifest activation history",
    description="""
GET /v1/admin/processes/history/manifests – View deployment history of model bundles

**Why we need this endpoint:**
- Admins need to track when and how model configurations were deployed to the platform
- Essential for compliance and audit requirements to know who deployed what and when
- Helps troubleshoot issues by understanding which manifest versions are active or failed
- Without this, there's no way to know the deployment history or rollback to previous versions

**What it does:**
- Shows the complete activation timeline of built-in manifest deployments
- Displays manifest name, version, activation time, and deployment status
- Tracks who activated each manifest (actor/user)
- Provides notes field for deployment context or troubleshooting information
- Enables filtering by manifest name, status, and time range

**Access:**
- Admin only – requires `admin:all` permission
- Returns 401 for missing/invalid tokens
- Returns 403 for non-admin users

**Behavior:**
- **Data source**: Queries PostgreSQL for persistent deployment records
- **Sorting**: Most recent activations first (newest to oldest)
- **Pagination**: Default 100 results, max 1000 per request
- **Filters available**:
  - `manifest_name`: Name of the manifest bundle
  - `status`: Deployment status (staged, active, rolled_back, failed)
  - `since`: ISO 8601 timestamp to see activations after a specific time
  - `limit`: Number of results (1-1000)

**Responses:**
- 200: OK – Successfully retrieved manifest history with deployment records
- 401: Unauthorized – Missing or invalid authentication token
- 403: Forbidden – User lacks admin:all permission
- 422: Unprocessable Entity – Invalid status filter value
- 500: Internal Server Error – Database query failed

**Examples:**
```bash
# Get all manifest activations
curl -X GET "http://localhost:8000/v1/admin/processes/history/manifests" \\
     -H "Authorization: Bearer $ADMIN_TOKEN"

# Filter by status and limit results
curl -X GET "http://localhost:8000/v1/admin/processes/history/manifests?status=active&limit=20" \\
     -H "Authorization: Bearer $ADMIN_TOKEN"

# Get history for specific manifest
curl -X GET "http://localhost:8000/v1/admin/processes/history/manifests?manifest_name=llama-bundle" \\
     -H "Authorization: Bearer $ADMIN_TOKEN"
```
    """,
    responses={
        200: {"description": "Manifest history retrieved successfully"},
        401: {"description": "Unauthorized - invalid or missing token"},
        403: {"description": "Forbidden - requires admin:all permission"},
        500: {"description": "Internal server error"},
    },
)
async def get_manifest_history_endpoint(
    request: Request,
    user: Principal = Depends(require_admin()),
    db: Session = Depends(get_db),
    manifest_name: str | None = Query(None, description="Filter by manifest name"),
    manifest_status: str | None = Query(None, alias="status", description="Filter by status"),
    since: datetime | None = Query(None, description="Filter after this ISO 8601 timestamp"),
    limit: int = Query(100, ge=1, le=1000, description="Max results to return"),
    x_correlation_id: str | None = Header(None),
) -> ManifestHistoryResponse:
    """Get manifest activation history."""
    start_time = time.time()
    correlation_id = _get_correlation_id(request, x_correlation_id)

    try:
        # Convert status string to enum if provided
        status_enum = None
        if manifest_status:
            try:
                status_enum = ManifestStatus(manifest_status)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Invalid status: {manifest_status}. Must be one of: staged, active, rolled_back, failed",
                )

        records, next_cursor = get_manifest_history(
            db=db,
            limit=limit,
            manifest_name=manifest_name,
            status=status_enum,
            since=since,
        )

        duration_ms = (time.time() - start_time) * 1000
        _emit_audit_log(
            actor=user.sub,
            action="get_manifest_history",
            resource="/v1/admin/processes/history/manifests",
            correlation_id=correlation_id,
            params={"manifest_name": manifest_name, "status": manifest_status, "limit": limit},
            result="success",
            duration_ms=duration_ms,
        )

        manifests = [
            {
                "id": str(r.id),
                "manifest_name": r.manifest_name,
                "version": r.version,
                "status": r.status.value,
                "activated_at": r.activated_at,
                "activated_by": r.activated_by,
                "notes": r.notes,
            }
            for r in records
        ]

        return ManifestHistoryResponse(manifests=manifests, next_cursor=next_cursor)

    except HTTPException:
        raise
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error(f"Failed to get manifest history: {e}", exc_info=True)
        _emit_audit_log(
            actor=user.sub,
            action="get_manifest_history",
            resource="/v1/admin/processes/history/manifests",
            correlation_id=correlation_id,
            params={"manifest_name": manifest_name, "status": manifest_status, "limit": limit},
            result="error",
            duration_ms=duration_ms,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "type": "about:blank",
                "title": "Internal Server Error",
                "status": 500,
                "detail": "Failed to retrieve manifest history",
                "instance": str(request.url),
                "correlation_id": correlation_id,
            },
        )


@router.get(
    "/history/processes",
    response_model=ProcessHistoryResponse,
    summary="Get process lifecycle event history",
    description="""
GET /v1/admin/processes/history/processes – View complete audit trail of process events

**Why we need this endpoint:**
- Admins need detailed forensic data to investigate process crashes, restarts, or performance issues
- Required for compliance to maintain complete audit logs of all process lifecycle events
- Essential for debugging by reconstructing exactly what happened to processes over time
- Without this, troubleshooting process issues would rely on scattered logs with no structured history

**What it does:**
- Returns complete timeline of all process lifecycle events (start, heartbeat, stop, exit, signal)
- Shows full metadata for each event: PID, port, artifact, timestamp, exit codes, and reasons
- Tracks which tenant and manifest version each process belonged to
- Provides powerful filtering to narrow down specific processes or time periods
- Enables reconstruction of process behavior over time for root cause analysis

**Access:**
- Admin only – requires `admin:all` permission
- Returns 401 for missing/invalid tokens
- Returns 403 for non-admin users

**Behavior:**
- **Data source**: Queries PostgreSQL for persistent audit logs
- **Sorting**: Most recent events first (newest to oldest)
- **Pagination**: Default 100 results, max 1000 per request
- **Filters available**:
  - `artifact`: Model name (e.g., "llama3-8b")
  - `pid`: Operating system process ID
  - `process_id`: Stable internal process identifier
  - `tenant_id`: Filter by tenant
  - `event`: Event type (start, heartbeat, stop, exit, signal)
  - `since`: ISO 8601 timestamp to see events after a specific time
  - `limit`: Number of results (1-1000)

**Responses:**
- 200: OK – Successfully retrieved process event history with full event details
- 401: Unauthorized – Missing or invalid authentication token
- 403: Forbidden – User lacks admin:all permission
- 422: Unprocessable Entity – Invalid event filter value
- 500: Internal Server Error – Database query failed

**Examples:**
```bash
# Get all process events
curl -X GET "http://localhost:8000/v1/admin/processes/history/processes" \\
     -H "Authorization: Bearer $ADMIN_TOKEN"

# Filter by artifact and event type
curl -X GET "http://localhost:8000/v1/admin/processes/history/processes?artifact=whisper&event=start" \\
     -H "Authorization: Bearer $ADMIN_TOKEN"

# Get events for specific PID
curl -X GET "http://localhost:8000/v1/admin/processes/history/processes?pid=42789" \\
     -H "Authorization: Bearer $ADMIN_TOKEN"

# Filter by time range
curl -X GET "http://localhost:8000/v1/admin/processes/history/processes?since=2025-10-21T10:00:00Z&limit=100" \\
     -H "Authorization: Bearer $ADMIN_TOKEN"
```
    """,
    responses={
        200: {"description": "Process history retrieved successfully"},
        401: {"description": "Unauthorized - invalid or missing token"},
        403: {"description": "Forbidden - requires admin:all permission"},
        500: {"description": "Internal server error"},
    },
)
async def get_process_history_endpoint(
    request: Request,
    user: Principal = Depends(require_admin()),
    db: Session = Depends(get_db),
    artifact: str | None = Query(None, description="Filter by artifact name"),
    pid: int | None = Query(None, description="Filter by OS process ID"),
    process_id: str | None = Query(None, description="Filter by process identifier"),
    tenant_id: str | None = Query(None, description="Filter by tenant ID"),
    event: str | None = Query(None, description="Filter by event type"),
    since: datetime | None = Query(None, description="Filter after this ISO 8601 timestamp"),
    limit: int = Query(100, ge=1, le=1000, description="Max results to return"),
    x_correlation_id: str | None = Header(None),
) -> ProcessHistoryResponse:
    """Get process lifecycle event history."""
    start_time = time.time()
    correlation_id = _get_correlation_id(request, x_correlation_id)

    try:
        # Convert event string to enum if provided
        event_enum = None
        if event:
            try:
                event_enum = ProcessEvent(event)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Invalid event: {event}. Must be one of: start, heartbeat, stop, exit, signal",
                )

        events, next_cursor = get_process_history(
            db=db,
            limit=limit,
            artifact=artifact,
            pid=pid,
            process_id=process_id,
            tenant_id=tenant_id,
            event=event_enum,
            since=since,
        )

        duration_ms = (time.time() - start_time) * 1000
        _emit_audit_log(
            actor=user.sub,
            action="get_process_history",
            resource="/v1/admin/processes/history/processes",
            correlation_id=correlation_id,
            params={"artifact": artifact, "pid": pid, "event": event, "limit": limit},
            result="success",
            duration_ms=duration_ms,
        )

        event_records = [
            {
                "id": str(e.id),
                "process_id": e.process_id,
                "artifact": e.artifact,
                "pid": e.pid,
                "port": e.port,
                "event": e.event.value,
                "reason": e.reason,
                "exit_code": e.exit_code,
                "ts": e.ts,
                "tenant_id": e.tenant_id,
                "manifest_version": e.manifest_version,
                "host": e.host,
            }
            for e in events
        ]

        return ProcessHistoryResponse(events=event_records, next_cursor=next_cursor)

    except HTTPException:
        raise
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error(f"Failed to get process history: {e}", exc_info=True)
        _emit_audit_log(
            actor=user.sub,
            action="get_process_history",
            resource="/v1/admin/processes/history/processes",
            correlation_id=correlation_id,
            params={"artifact": artifact, "pid": pid, "event": event, "limit": limit},
            result="error",
            duration_ms=duration_ms,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "type": "about:blank",
                "title": "Internal Server Error",
                "status": 500,
                "detail": "Failed to retrieve process history",
                "instance": str(request.url),
                "correlation_id": correlation_id,
            },
        )


# ---------------- Legacy compatibility ----------------
@router.post("/{pid}:stop", include_in_schema=False)
async def stop_process_legacy(pid: int):
    """Legacy compatibility: inform clients the route has moved.

    Returns 410 Gone to indicate removal; kept hidden from OpenAPI.
    """
    return JSONResponse(
        status_code=410,
        content={
            "type": "about:blank",
            "title": "Gone",
            "status": 410,
            "detail": "This endpoint is deprecated. Use DELETE /v1/admin/processes/{pid} instead.",
        },
    )
