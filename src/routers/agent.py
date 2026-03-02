"""
Agent orchestration endpoint with stateful sessions.

Endpoints:
- POST /agents/sessions - Create new agent session
- GET /agents/sessions - List user's sessions
- GET /agents/sessions/{id} - Get session details
- DELETE /agents/sessions/{id} - Cancel session
- GET /agents/sessions/{id}/steps - List session steps
- POST /agents/sessions/{id}/steps - Add step to session

For runs see `src.routers.agent_runs` (mounted at /v1/agent-runs).
"""

from __future__ import annotations

import uuid
from contextlib import suppress
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session as DBSession

from db.postgres_control.database import get_db
from db.postgres_control.repositories.agents import (
    AgentSessionRepository,
    AgentStepRepository,
)
from db.redis_cache.agents import (
    allocate_next_seq,
    get_session_state,
    invalidate_sessions_etag,
    invalidate_steps_etag,
    session_lock,
    set_session_cancelled,
    set_session_state,
)
from src.errors import agents as agent_errors
from src.middleware.idempotency import IdempotencyHandler
from src.middleware.rate_limit import RateLimitHandler, add_rate_limit_headers
from src.provenance import record_provenance
from src.schemas.auth import UserInfo
from src.routers.auth import get_current_user
from src.schemas.agents import (
    CreateSessionRequest,
    CreateStepRequest,
    SessionListItem,
    SessionListResponse,
    SessionResponse,
    StepListResponse,
    StepResponse,
)
from src.security.perm import require_perms
from src.services.session_fallback import SessionFallbackStore
from src.utils.etag import generate_etag, validate_etag

# Tool policy integration (P1.3)
with suppress(Exception):
    from src.mcp import list_tool_names  # type: ignore
    from src.mcp.tool_policy import filter_tools  # type: ignore

if "filter_tools" not in globals():

    def filter_tools(*args, **kwargs):  # type: ignore
        """Fallback if tool_policy not available."""
        return kwargs.get("available_tools", [])

    def list_tool_names(**kwargs):  # type: ignore
        """Fallback if mcp not available."""
        return []


router = APIRouter(tags=["agents"])


# Helper to get request ID from context
def get_request_id() -> str | None:
    """Get the current request ID from context."""
    try:
        from src.app import _request_id_ctx

        return _request_id_ctx.get()
    except Exception:
        return None


def add_standard_headers(headers: dict, request_id: str | None = None) -> dict:
    """Add standard headers to response: X-Request-Id, Vary."""
    rid = request_id or get_request_id()
    if rid:
        headers.setdefault("X-Request-Id", rid)
    return headers


def _get_session_with_fallback(db: DBSession, session_id: UUID, user_id: str):
    if SessionFallbackStore.is_db_available():
        try:
            return AgentSessionRepository.get_by_id_and_owner(db, session_id, user_id)
        except Exception as exc:  # Database unreachable or query error
            db.rollback()
            if SessionFallbackStore.should_use_fallback(exc):
                SessionFallbackStore.mark_db_unavailable(exc)
            else:
                agent_errors.database_error(
                    operation="load session",
                    error=str(exc),
                    instance=f"/agents/sessions/{session_id}",
                )
    return SessionFallbackStore.get_for_owner(session_id, user_id)


def _create_session_with_fallback(
    db: DBSession,
    *,
    session_id: UUID,
    user_id: str,
    tenant_id: str,
    manager: str | None,
    tools: list[str] | None,
    temperature: float,
    max_steps: int,
    metadata: dict[str, Any],
):
    if SessionFallbackStore.is_db_available():
        try:
            session = AgentSessionRepository.create(
                db,
                session_id=session_id,
                user_id=user_id,
                tenant_id=tenant_id,
                manager=manager,
                tools=tools,
                temperature=temperature,
                max_steps=max_steps,
                metadata=metadata,
            )
            db.commit()
            return session
        except Exception as exc:
            db.rollback()
            if SessionFallbackStore.should_use_fallback(exc):
                SessionFallbackStore.mark_db_unavailable(exc)
            else:
                error_text = str(exc)
                lowered = error_text.lower()
                if "unique" in lowered or "duplicate" in lowered:
                    agent_errors.duplicate_session(
                        session_id=session_id,
                        instance=f"/agents/sessions/{session_id}",
                    )
                agent_errors.database_error(
                    operation="create session",
                    error=error_text,
                    instance="/agents/sessions",
                )

    return SessionFallbackStore.create(
        session_id=session_id,
        user_id=user_id,
        tenant_id=tenant_id,
        manager=manager,
        tools=tools,
        temperature=temperature,
        max_steps=max_steps,
        metadata=metadata,
    )


# Back-compat alias: expose colon action /v1/agents:run that forwards to the
# canonical agent run endpoint in `agent_runs`.
try:
    from src.routers.agent_runs import (
        AgentRequest as _AgentRequest,
        create_agent_run as _create_agent_run,  # type: ignore
    )

    @router.post(path=":run", include_in_schema=False)
    async def _run_alias(
        request: Request, response: JSONResponse, user: UserInfo = Depends(require_perms(["user:me"]))
    ):
        try:
            body = await request.json()
        except Exception:
            body = {}
        req = _AgentRequest(**(body or {}))
        return await _create_agent_run(request, req, response, user)  # type: ignore

except Exception:
    pass


# ---------------- Agent sessions (stateful sessions) ----------------


@router.post(
    "/sessions",
    summary="Create a new agent session",
    name="create_session",
    status_code=status.HTTP_201_CREATED,
    response_model=SessionResponse,
    description=(
        "**Why we need this endpoint:**\n"
        "- Start long-running conversations where context and memory persist across multiple steps\n"
        "- Set up configurations (LLM choice, available tools, temperature) before sending work\n"
        "- Track related tasks together as a single workflow unit\n"
        "- Enable pausing, continuing, or cancelling work in progress\n\n"
        "**What it does:**\n"
        "- Creates a session with a unique ID you can reference later\n"
        "- Stores your session preferences (temperature, max steps, allowed tools)\n"
        "- Optionally accepts a session ID for idempotency\n"
        "- Returns full session details so you can start adding steps immediately\n"
        "- Sending the same Idempotency-Key returns the same session without creating duplicates\n\n"
        "**Access:** Authenticated users can create sessions; users see only their own, admins see all\n\n"
        "**Behavior:** Supports idempotency (same request = same response), rate limiting, multi-tenant isolation"
    ),
    responses={
        201: {
            "description": "Session created successfully with assigned ID and sequence number",
            "model": SessionResponse,
            "headers": {
                "Location": {"description": "URI to the created session for GET requests"},
                "Idempotency-Key": {"description": "Echo of the Idempotency-Key header if provided"},
                "X-Request-Id": {"description": "Request correlation ID for tracing"},
            },
        },
        200: {
            "description": "Session already exists - returned from idempotent replay or existing session_id",
            "model": SessionResponse,
            "headers": {
                "Location": {"description": "URI to the existing session"},
                "Idempotency-Key": {"description": "Echo of the Idempotency-Key header if provided"},
                "Idempotency-Replayed": {
                    "description": "Set to 'true' when returning cached result from idempotent replay"
                },
                "X-Request-Id": {"description": "Request correlation ID for tracing"},
            },
        },
        400: {
            "description": "Bad Request - Invalid request body (e.g., temperature out of range)",
            "content": {
                "application/problem+json": {
                    "schema": {"$ref": "#/components/schemas/ProblemDetails"},
                    "example": {
                        "type": "about:blank",
                        "title": "Bad Request",
                        "status": 400,
                        "detail": "temperature must be between 0.0 and 2.0",
                        "instance": "/v1/agents/sessions",
                        "extensions": {"correlation_id": "req-123456", "timestamp": "2025-10-21T10:30:00Z"},
                    },
                }
            },
        },
        409: {
            "description": "Conflict - session_id already exists and belongs to another user",
            "content": {
                "application/problem+json": {
                    "schema": {"$ref": "#/components/schemas/ProblemDetails"},
                    "example": {
                        "type": "about:blank",
                        "title": "Conflict",
                        "status": 409,
                        "detail": "Session with ID already exists",
                        "instance": "/v1/agents/sessions",
                        "extensions": {"correlation_id": "req-123456", "timestamp": "2025-10-21T10:30:00Z"},
                    },
                }
            },
        },
    },
)
async def create_session(
    req: CreateSessionRequest,
    request: Request,
    response: Response,
    db: DBSession = Depends(get_db),
    user: UserInfo = Depends(require_perms(["user:me"])),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    """Create new agent session with idempotency support."""
    # Check rate limit first
    rate_limiter = RateLimitHandler(user_id=user.sub)
    await rate_limiter.check("sessions:create")

    handler = IdempotencyHandler(request, response, user.sub, db, idempotency_key)

    # Check for replay (idempotent request)
    if idempotency_key:
        cached = handler.check()
        if cached:
            # Extract response body from cached result
            cached_body = cached.get("body", cached)

            # Set Location header for replay too
            session_id_replay = cached_body.get("session_id")
            try:
                loc = request.url_for("get_session", session_id=session_id_replay)
            except Exception:
                loc = f"/v1/agents/sessions/{session_id_replay}"

            # Build headers for idempotent replay
            headers = {
                "Idempotency-Replayed": "true",
                "Location": str(loc),
                "Idempotency-Key": idempotency_key,
            }

            # Add standard headers (X-Request-Id)
            headers = add_standard_headers(headers)

            # Return 200 for idempotent replay (not 201)
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=cached_body,
                headers=headers,
            )

    # If session_id provided, check ownership and return existing
    if req.session_id:
        existing = _get_session_with_fallback(db, req.session_id, user.sub)
        if existing:
            # Return 200 OK for existing owned session (already exists)
            # Set Location header
            try:
                loc = request.url_for("get_session", session_id=req.session_id)
            except Exception:
                loc = f"/v1/agents/sessions/{req.session_id}"

            result = SessionResponse.model_validate(existing)

            # Build headers
            headers = {"Location": str(loc)}
            if idempotency_key:
                headers["Idempotency-Key"] = idempotency_key

            # Add standard headers (X-Request-Id)
            headers = add_standard_headers(headers)

            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=result.model_dump(mode="json"),
                headers=headers,
            )

    # Create new session
    session_id = req.session_id or uuid.uuid4()
    session_id_str = str(session_id)

    # Get tenant_id (required for multi-tenancy)
    # Use tenant from JWT if available, otherwise use default tenant
    tenant_id = getattr(user, "tenant_id", None) or user.raw.get("tid", "tenant-67e5ca68")

    # P1.3: Filter tools by agent role and session allowlist
    # This enforces tool policy before session creation
    all_available_tools = list_tool_names()
    allowed_tools = filter_tools(
        available_tools=all_available_tools,
        agent_role=req.agent_role,
        session_tools=req.tools,  # explicit allowlist from request
    )

    # Log tool filtering for audit trail
    with suppress(Exception):
        from src.logging_setup import get_logger

        logger = get_logger(__name__)
        logger.info(
            "Tool policy applied to session",
            extra={
                "session_id": session_id_str,
                "agent_role": req.agent_role,
                "requested_tools": len(req.tools) if req.tools else 0,
                "allowed_tools": len(allowed_tools),
                "user_id": user.sub,
            },
        )

    session = _create_session_with_fallback(
        db,
        session_id=session_id,
        user_id=user.sub,
        tenant_id=tenant_id,
        manager=req.manager,
        tools=allowed_tools,  # Use filtered tools (not raw request.tools)
        temperature=req.temperature,
        max_steps=req.max_steps,
        metadata=req.metadata or {},
    )

    # Initialize Redis state
    set_session_state(
        session_id,
        {
            "status": "active",
            "user_id": user.sub,
            "created_at": session.created_at.isoformat(),
        },
    )

    # Invalidate user's sessions ETag
    invalidate_sessions_etag(user.sub)

    # Record provenance
    record_provenance(
        actor="api",
        action="agents.sessions.create",
        resource=f"/agents/sessions/{session_id_str}",
        input=req.model_dump(mode="json"),
        output={"session_id": str(session_id)},
        meta={"user": user.sub},
        success=True,
    )

    # Build response
    result = SessionResponse.model_validate(session)
    result_dict = result.model_dump(mode="json")

    # Cache idempotent result with 201 status (since this is a create operation)
    if idempotency_key:
        await handler.cache(
            request_body=req.model_dump(mode="json"),
            response_body=result_dict,
            status_code=status.HTTP_201_CREATED,
        )

    # Set Location header
    try:
        loc = request.url_for("get_session", session_id=session_id_str)
    except Exception:
        loc = f"/v1/agents/sessions/{session_id_str}"

    # Prepare headers
    headers = {"Location": str(loc)}

    # Add Idempotency-Key response header if provided
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key

    # Add standard headers (X-Request-Id)
    headers = add_standard_headers(headers)

    # Add rate limit headers
    await add_rate_limit_headers(response, user.sub, "sessions:create")
    headers.update(response.headers)

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=result_dict,
        headers=headers,
    )


@router.get(
    "/sessions",
    summary="List agent sessions",
    name="list_sessions",
    response_model=SessionListResponse,
    description=(
        "**Why we need this endpoint:**\n"
        "- Find sessions you've started to continue or monitor them\n"
        "- Track status of ongoing work (active, completed, cancelled)\n"
        "- Navigate through your conversation and workflow history\n"
        "- Handle pagination efficiently for large numbers of sessions\n\n"
        "**What it does:**\n"
        "- Returns a paginated list of your sessions (or all sessions if you're admin)\n"
        "- Includes minimal info per session (ID, status, dates, last step sequence)\n"
        "- Supports cursor-based pagination for efficient navigation\n"
        "- Caches results with ETag to avoid redundant responses\n\n"
        "**Access:** Users see only their own sessions; admins see all; authenticated users only\n\n"
        "**Behavior:** Cursor-based pagination (limit=20 default), ETag caching (304 if unchanged), rate limiting, ordered by most recent update"
    ),
    responses={
        200: {
            "description": "Sessions listed successfully with pagination support",
            "model": SessionListResponse,
            "headers": {
                "ETag": {"description": "Entity tag for caching support (If-None-Match)"},
                "Vary": {"description": "Indicates that response varies by Authorization header"},
                "X-Request-Id": {"description": "Request correlation ID for tracing"},
            },
        },
        304: {"description": "Not Modified - session list unchanged since last request (ETag matched)"},
    },
)
async def list_sessions(
    request: Request,
    response: Response,
    limit: int = 20,
    cursor: str | None = None,
    db: DBSession = Depends(get_db),
    user: UserInfo = Depends(require_perms(["user:me"])),
    if_none_match: str | None = Header(None, alias="If-None-Match"),
):
    """List sessions with ETag caching and pagination."""
    # Check rate limit for list operations
    rate_limiter = RateLimitHandler(user_id=user.sub)
    await rate_limiter.check("sessions:list")

    is_admin = "admin:all" in user.scopes

    # Query sessions
    if is_admin:
        sessions, next_token = AgentSessionRepository.list_all(
            db,
            page_size=limit,
            page_token=cursor,
        )
    else:
        sessions, next_token = AgentSessionRepository.list_by_user(
            db,
            user_id=user.sub,
            page_size=limit,
            page_token=cursor,
        )

    # Enrich with Redis state
    items = []
    for session in sessions:
        state = get_session_state(session.session_id)
        # Use SessionListItem for list responses (minimal fields)
        item_dict = {
            "session_id": session.session_id,
            "status": state.get("status") if state else session.status,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "last_step_seq": session.last_step_seq,
            "manager": session.manager,
        }
        items.append(SessionListItem(**item_dict))

    result = SessionListResponse(items=items, next_cursor=next_token)

    # Generate and validate ETag
    result_dict = result.model_dump(mode="json")
    current_etag = generate_etag(result_dict, weak=False)

    # Check If-None-Match header
    if validate_etag(if_none_match, current_etag):
        headers = {"ETag": current_etag, "Vary": "Authorization"}
        headers = add_standard_headers(headers)
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=result_dict,
        headers=add_standard_headers(
            {
                "ETag": current_etag,
                "Vary": "Authorization",
            }
        ),
    )


@router.get(
    "/sessions/{session_id}",
    summary="Get session details",
    name="get_session",
    response_model=SessionResponse,
    description=(
        "**Why we need this endpoint:**\n"
        "- Check current session status (is it active, completed, failed?)\n"
        "- View session configuration and parameters (temperature, tools, max steps)\n"
        "- Track metadata and lifecycle timestamps\n"
        "- Get ID of the most recent step for progress checking\n\n"
        "**What it does:**\n"
        "- Retrieves all details about a session you own or admin has access to\n"
        "- Includes session status, full configuration, creation/update timestamps\n"
        "- Provides ID of the most recent step (useful for tracking progress)\n"
        "- Supports ETag caching for efficient repeated checks\n"
        "- Validates you have permission to view this specific session\n\n"
        "**Access:** Users see only their own sessions; admins can see any session; authenticated only\n\n"
        "**Behavior:** Ownership validation, ETag support (304 if unchanged), returns 404 if not found or not accessible"
    ),
    responses={
        200: {
            "description": "Session found and returned with full details",
            "model": SessionResponse,
            "headers": {
                "ETag": {"description": "Entity tag for caching support (If-None-Match)"},
                "Vary": {"description": "Indicates that response varies by Authorization header"},
                "X-Request-Id": {"description": "Request correlation ID for tracing"},
            },
        },
        304: {"description": "Not Modified - session details unchanged since last check (ETag matched)"},
        404: {
            "description": "Not Found - Session not found or you don't have permission to view it",
            "content": {
                "application/problem+json": {
                    "schema": {"$ref": "#/components/schemas/ProblemDetails"},
                    "example": {
                        "type": "about:blank",
                        "title": "Not Found",
                        "status": 404,
                        "detail": "Session not found",
                        "instance": "/v1/agents/sessions/{session_id}",
                        "extensions": {"correlation_id": "req-123456", "timestamp": "2025-10-21T10:30:00Z"},
                    },
                }
            },
        },
    },
)
async def get_session(
    session_id: str,
    response: Response,
    db: DBSession = Depends(get_db),
    user: UserInfo = Depends(require_perms(["user:me"])),
    if_none_match: str | None = Header(None, alias="If-None-Match"),
):
    """Get session by ID with ownership check and ETag support."""
    is_admin = "admin:all" in user.scopes

    try:
        # Get session with ownership check
        if is_admin:
            session = AgentSessionRepository.get_by_id(db, session_id)
        else:
            session = AgentSessionRepository.get_by_id_and_owner(db, session_id, user.sub)
    except (ValueError, Exception):
        # Invalid UUID format
        agent_errors.session_not_found(
            session_id=session_id,
            instance=f"/agents/sessions/{session_id}",
        )

    if not session:
        agent_errors.session_not_found(
            session_id=session_id,
            instance=f"/agents/sessions/{session_id}",
        )

    # Enrich with Redis state
    state = get_session_state(session_id)
    result = SessionResponse.model_validate(session)
    if state and "status" in state:
        result.status = state["status"]

    # Generate and validate ETag
    result_dict = result.model_dump(mode="json")
    current_etag = generate_etag(result_dict, weak=False)

    # Check If-None-Match header
    if validate_etag(if_none_match, current_etag):
        headers = {"ETag": current_etag, "Vary": "Authorization"}
        headers = add_standard_headers(headers)
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=result_dict,
        headers=add_standard_headers(
            {
                "ETag": current_etag,
                "Vary": "Authorization",
            }
        ),
    )


@router.delete(
    "/sessions/{session_id}",
    summary="Cancel agent session",
    name="cancel_session",
    status_code=status.HTTP_204_NO_CONTENT,
    description=(
        "**Why we need this endpoint:**\n"
        "- Stop sessions running longer than expected or no longer needed\n"
        "- Signal backend to clean up resources and halt ongoing work\n"
        "- Enable graceful exit from long-running conversations\n"
        "- Safe to call multiple times (idempotent) with no side effects\n\n"
        "**What it does:**\n"
        "- Marks the session as 'cancelled' in the database\n"
        "- Signals any running orchestrator/worker to stop processing\n"
        "- Returns immediately without waiting for cleanup completion\n"
        "- Is idempotent: calling multiple times is safe and produces the same result\n\n"
        "**Access:** Users can cancel their own sessions; admins can cancel any; authenticated only\n\n"
        "**Behavior:** Idempotent (safe to call twice), best-effort (no guarantee of immediate stop), subsequent GET shows 'cancelled' status, returns 204 No Content (no response body)"
    ),
    responses={
        204: {
            "description": "Cancellation request accepted and processed successfully - no content returned",
            "headers": {
                "X-Request-Id": {"description": "Request correlation ID for tracing"},
            },
        },
        404: {
            "description": "Not Found - Session not found or you don't have permission to cancel it",
            "content": {
                "application/problem+json": {
                    "schema": {"$ref": "#/components/schemas/ProblemDetails"},
                    "example": {
                        "type": "about:blank",
                        "title": "Not Found",
                        "status": 404,
                        "detail": "Session not found",
                        "instance": "/v1/agents/sessions/{session_id}",
                        "extensions": {"correlation_id": "req-123456", "timestamp": "2025-10-21T10:30:00Z"},
                    },
                }
            },
        },
    },
)
async def cancel_session(
    session_id: str,
    db: DBSession = Depends(get_db),
    user: UserInfo = Depends(require_perms(["user:me"])),
):
    """Cancel session with ownership check."""
    is_admin = "admin:all" in user.scopes

    try:
        # Check ownership
        if is_admin:
            session = AgentSessionRepository.get_by_id(db, session_id)
        else:
            session = AgentSessionRepository.get_by_id_and_owner(db, session_id, user.sub)
    except (ValueError, Exception):
        # Invalid UUID format
        agent_errors.session_not_found(
            session_id=session_id,
            instance=f"/agents/sessions/{session_id}",
        )

    if not session:
        agent_errors.session_not_found(
            session_id=session_id,
            instance=f"/agents/sessions/{session_id}",
        )

    # Set cancellation flag in Redis
    with session_lock(session_id):
        set_session_cancelled(session_id)

        # Update session state in Redis to reflect cancelled status
        state = get_session_state(session_id) or {}
        state["status"] = "cancelled"
        set_session_state(session_id, state)

        # Update DB status
        AgentSessionRepository.update_status(db, session_id, "cancelled")
        db.commit()

    # Invalidate ETags
    invalidate_sessions_etag(user.sub)

    # Record provenance
    record_provenance(
        actor="api",
        action="agents.sessions.cancel",
        resource=f"/agents/sessions/{session_id}",
        input={},
        output={"ok": True},
        meta={"user": user.sub},
        success=True,
    )

    headers = add_standard_headers({})
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=headers)


@router.get(
    "/sessions/{session_id}/steps",
    summary="List session steps",
    name="list_session_steps",
    response_model=StepListResponse,
    description=(
        "**Why we need this endpoint:**\n"
        "- Track what the agent has done (tools used, messages sent, errors encountered)\n"
        "- Review step-by-step progression of the session workflow\n"
        "- Debug issues by examining individual step results and inputs\n"
        "- Handle pagination for sessions with many steps\n\n"
        "**What it does:**\n"
        "- Returns paginated list of all steps in a session, ordered by sequence number\n"
        "- Each step shows type (message, tool call, error), content, and status\n"
        "- Includes timestamps for creation and completion\n"
        "- Supports cursor-based pagination for efficient loading\n"
        "- Caches results with ETag for bandwidth savings\n\n"
        "**Access:** Users see steps only for their own sessions; admins see any; authenticated only\n\n"
        "**Behavior:** Cursor-based pagination (limit=50 default), ETag caching (304 if unchanged), rate limiting, ordered oldest-to-newest by sequence"
    ),
    responses={
        200: {
            "description": "Steps listed successfully with pagination support",
            "model": StepListResponse,
            "headers": {
                "ETag": {"description": "Entity tag for caching support (If-None-Match)"},
                "Vary": {"description": "Indicates that response varies by Authorization header"},
                "X-Request-Id": {"description": "Request correlation ID for tracing"},
            },
        },
        304: {"description": "Not Modified - step list unchanged since last check (ETag matched)"},
        404: {
            "description": "Not Found - Session not found or you don't have permission to view it",
            "content": {
                "application/problem+json": {
                    "schema": {"$ref": "#/components/schemas/ProblemDetails"},
                    "example": {
                        "type": "about:blank",
                        "title": "Not Found",
                        "status": 404,
                        "detail": "Session not found",
                        "instance": "/v1/agents/sessions/{session_id}/steps",
                        "extensions": {"correlation_id": "req-123456", "timestamp": "2025-10-21T10:30:00Z"},
                    },
                }
            },
        },
    },
)
async def list_session_steps(
    session_id: str,
    request: Request,
    response: Response,
    limit: int = 50,
    cursor: str | None = None,
    db: DBSession = Depends(get_db),
    user: UserInfo = Depends(require_perms(["user:me"])),
    if_none_match: str | None = Header(None, alias="If-None-Match"),
):
    """List session steps with ETag caching."""
    # Check rate limit
    rate_limiter = RateLimitHandler(user_id=user.sub, resource_id=session_id)
    await rate_limiter.check("steps:list")

    is_admin = "admin:all" in user.scopes

    try:
        # Check session ownership
        if is_admin:
            session = AgentSessionRepository.get_by_id(db, session_id)
        else:
            session = AgentSessionRepository.get_by_id_and_owner(db, session_id, user.sub)
    except (ValueError, Exception):
        # Invalid UUID format
        agent_errors.session_not_found(
            session_id=session_id,
            instance=f"/agents/sessions/{session_id}/steps",
        )

    if not session:
        agent_errors.session_not_found(
            session_id=session_id,
            instance=f"/agents/sessions/{session_id}/steps",
        )

    # Query steps
    steps, next_token = AgentStepRepository.list_by_session(
        db,
        session_id=session_id,
        page_size=limit,
        page_token=cursor,
    )

    # Build response
    items = [StepResponse.model_validate(step) for step in steps]
    result = StepListResponse(items=items, next_cursor=next_token)

    # Generate and validate ETag
    result_dict = result.model_dump(mode="json")
    current_etag = generate_etag(result_dict, weak=False)

    # Check If-None-Match header
    if validate_etag(if_none_match, current_etag):
        headers = {"ETag": current_etag, "Vary": "Authorization"}
        headers = add_standard_headers(headers)
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=result_dict,
        headers=add_standard_headers(
            {
                "ETag": current_etag,
                "Vary": "Authorization",
            }
        ),
    )


@router.post(
    "/sessions/{session_id}/steps",
    summary="Add step to session",
    name="create_session_step",
    status_code=status.HTTP_201_CREATED,
    response_model=StepResponse,
    description=(
        "**Why we need this endpoint:**\n"
        "- Add user messages to keep conversations going\n"
        "- Submit tool inputs and observe outputs\n"
        "- Feed system messages or errors back to the agent\n"
        "- Build interactive multi-turn agent workflows step-by-step\n\n"
        "**What it does:**\n"
        "- Creates a new step within the specified session\n"
        "- Automatically assigns the next sequence number\n"
        "- Stores step content (message, tool name, input/output data)\n"
        "- Marks step status as queued/received\n"
        "- Returns created step with assigned ID and sequence number\n"
        "- Validates session is active before accepting the step\n\n"
        "**Access:** Users can add steps to their own sessions; admins to any; authenticated only\n\n"
        "**Behavior:** Auto-sequencing, session must be 'active' (not cancelled/completed), supports idempotency (Idempotency-Key header), type validation (message/user/assistant/tool/system/error), async processing"
    ),
    responses={
        201: {
            "description": "Step created successfully with assigned ID and sequence number",
            "model": StepResponse,
            "headers": {
                "Location": {"description": "URI to the created step for future reference"},
                "Idempotency-Key": {"description": "Echo of the Idempotency-Key header if provided"},
                "Idempotency-Replayed": {"description": "Set to true if this was an idempotent replay"},
                "X-Request-Id": {"description": "Request correlation ID for tracing"},
            },
        },
        400: {
            "description": "Bad Request - Invalid request (invalid step type, session not active, etc.)",
            "content": {
                "application/problem+json": {
                    "schema": {"$ref": "#/components/schemas/ProblemDetails"},
                    "example": {
                        "type": "about:blank",
                        "title": "Bad Request",
                        "status": 400,
                        "detail": "Session is not active",
                        "instance": "/v1/agents/sessions/{session_id}/steps",
                        "extensions": {"correlation_id": "req-123456", "timestamp": "2025-10-21T10:30:00Z"},
                    },
                }
            },
        },
        404: {
            "description": "Not Found - Session not found or you don't have permission",
            "content": {
                "application/problem+json": {
                    "schema": {"$ref": "#/components/schemas/ProblemDetails"},
                    "example": {
                        "type": "about:blank",
                        "title": "Not Found",
                        "status": 404,
                        "detail": "Session not found",
                        "instance": "/v1/agents/sessions/{session_id}/steps",
                        "extensions": {"correlation_id": "req-123456", "timestamp": "2025-10-21T10:30:00Z"},
                    },
                }
            },
        },
    },
)
async def create_session_step(
    session_id: str,
    req: CreateStepRequest,
    request: Request,
    response: Response,
    db: DBSession = Depends(get_db),
    user: UserInfo = Depends(require_perms(["user:me"])),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    """Add step to session with sequencing."""
    # Check rate limit
    rate_limiter = RateLimitHandler(user_id=user.sub, resource_id=session_id)
    await rate_limiter.check("steps:create")

    is_admin = "admin:all" in user.scopes
    handler = IdempotencyHandler(request, response, user.sub, db, idempotency_key)

    # Check for replay
    if idempotency_key:
        cached = handler.check()
        if cached:
            # Extract status code and response body from cached result
            cached_body = cached.get("body", cached)
            cached_status = cached.get("status_code", 201)
            response.headers["Idempotency-Replayed"] = "true"
            return JSONResponse(
                status_code=cached_status,
                content=cached_body,
                headers={"Idempotency-Replayed": "true"},
            )

    try:
        # Get session with ownership check
        if is_admin:
            session = AgentSessionRepository.get_by_id(db, session_id)
        else:
            session = AgentSessionRepository.get_by_id_and_owner(db, session_id, user.sub)
    except (ValueError, Exception):
        # Invalid UUID format
        agent_errors.session_not_found(
            session_id=session_id,
            instance=f"/agents/sessions/{session_id}/steps",
        )

    if not session:
        agent_errors.session_not_found(
            session_id=session_id,
            instance=f"/agents/sessions/{session_id}/steps",
        )

    # Check session is active
    state = get_session_state(session_id)
    session_status = state.get("status") if state else session.status
    if session_status != "active":
        agent_errors.session_not_active(
            session_id=session_id,
            current_status=session_status,
            instance=f"/agents/sessions/{session_id}/steps",
        )

    # Allocate sequence number and create step
    with session_lock(session_id):
        seq = allocate_next_seq(session_id)

        step = AgentStepRepository.create(
            db,
            session_id=session_id,
            seq=seq,
            type=req.type,
            message=req.message,
            tool=req.tool,
            input=req.input,
            output=req.output,
        )

        # Update session's last_step_id and seq
        AgentSessionRepository.update_last_step(db, session_id, step.step_id, seq)

        db.commit()

    # Invalidate steps ETag
    invalidate_steps_etag(session_id)

    # Record provenance
    record_provenance(
        actor="api",
        action="agents.sessions.step",
        resource=f"/agents/sessions/{session_id}/steps/{step.step_id}",
        input=req.model_dump(mode="json"),
        output={"step_id": str(step.step_id), "seq": seq},
        meta={"user": user.sub},
        success=True,
    )

    # Build response
    result = StepResponse.model_validate(step)
    result_dict = result.model_dump(mode="json")

    # Cache idempotent result with 201 status (since this is a create operation)
    if idempotency_key:
        await handler.cache(
            request_body=req.model_dump(mode="json"),
            response_body=result_dict,
            status_code=status.HTTP_201_CREATED,
        )

    # Set Location header
    try:
        loc = f"{request.url.path}/{step.step_id}"
    except Exception:
        loc = f"/v1/agents/sessions/{session_id}/steps/{step.step_id}"

    # Prepare headers
    headers = {"Location": str(loc)}

    # Add Idempotency-Key response header if provided
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key

    # Add standard headers (X-Request-Id)
    headers = add_standard_headers(headers)

    # Add rate limit headers
    await add_rate_limit_headers(response, user.sub, "steps:create", resource_id=session_id)
    headers.update(response.headers)

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=result_dict,
        headers=headers,
    )
