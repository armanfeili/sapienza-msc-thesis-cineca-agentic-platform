"""
Admin-facing proxy for internal ops endpoints.

These routes mirror the behavior of /internal/ops/* but are gated with require_admin
instead of require_internal, allowing platform admins to perform the same operations
through the API without needing service tokens.

Storage and logic are shared with the internal endpoints to avoid drift.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from db.postgres_control.database import SessionLocal
from db.postgres_control.models.internal_ops_event import InternalOpsEvent
from db.redis_cache.async_client import get_async_redis
from src.config import settings
from src.security.admin import require_admin
from src.security.jwt import Principal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["admin-ops"])


# ============================================================================
# Shared Models (same as internal_ops)
# ============================================================================


class AutoStartOverrideRequest(BaseModel):
    """Request to override auto-start behavior for built-in models."""

    enabled: bool = Field(..., description="Whether to enable auto-start")
    note: str = Field(default="", max_length=500, description="Optional explanation for this override")


class AutoStartOverrideResponse(BaseModel):
    """Response from auto-start override operation."""

    allowed: bool = Field(..., description="Whether the override feature is enabled")
    enabled: bool = Field(..., description="Current auto-start state")
    ttl_seconds: int = Field(..., description="Time-to-live in seconds (0 if feature disabled or error)")
    error: str | None = Field(default=None, description="Error indicator if cache unavailable")


class PreviewStagedManifest(BaseModel):
    """A single manifest that would be deployed."""

    name: str
    version: str
    auto_start: bool
    source: str = Field(description="'builtin' or 'custom'")


class PreviewStagedResponse(BaseModel):
    """Response from preview-staged operation."""

    items: list[PreviewStagedManifest]
    count: int
    override_active: bool = Field(description="Whether auto-start override is currently active")
    timestamp: datetime


# ============================================================================
# Shared Service Functions
# ============================================================================


async def _write_override_to_redis(enabled: bool, ttl_seconds: int) -> dict:
    """
    Write auto-start override to Redis.

    Returns dict with {allowed, enabled, ttl_seconds, error?}
    Never raises exceptions - returns graceful error indicators.
    """
    try:
        redis = await get_async_redis()
        override_data = {"enabled": enabled, "timestamp": datetime.now(UTC).isoformat()}

        await redis.setex("internal:auto_start_override", ttl_seconds, json.dumps(override_data))

        return {"allowed": True, "enabled": enabled, "ttl_seconds": ttl_seconds, "error": None}
    except Exception as e:
        logger.warning(f"Failed to write override to Redis: {e}")
        return {"allowed": True, "enabled": enabled, "ttl_seconds": 0, "error": "cache_unavailable"}


async def _read_override_from_redis() -> tuple[bool, dict | None]:
    """
    Read auto-start override from Redis.

    Returns (override_active: bool, data: dict | None)
    """
    try:
        redis = await get_async_redis()
        raw = await redis.get("internal:auto_start_override")
        if raw:
            data = json.loads(raw)
            return (data.get("enabled", False), data)
        return (False, None)
    except Exception as e:
        logger.warning(f"Failed to read override from Redis: {e}")
        return (False, None)


def _audit_operation(actor_sub: str, kind: str, enabled: bool, note: str, data: dict) -> None:
    """
    Write audit event to PostgreSQL.

    Failures are logged but don't block the operation.
    """
    try:
        db = SessionLocal()
        event = InternalOpsEvent(kind=kind, sub=actor_sub, enabled=enabled, note=note or "", data_json=data)
        db.add(event)
        db.commit()
        logger.info(
            f"Audit: {kind} by {actor_sub}", extra={"kind": kind, "actor": actor_sub, "enabled": enabled, "data": data}
        )
    except Exception as e:
        logger.warning(f"Failed to write audit event: {e}")
    finally:
        if "db" in locals():
            db.close()


# ============================================================================
# Admin Routes (Proxy to Internal Logic)
# ============================================================================


@router.post(
    "/auto-start-override",
    response_model=AutoStartOverrideResponse,
    status_code=status.HTTP_200_OK,
    summary="Override auto-start behavior (Admin)",
    description="""
    Admin-facing proxy for internal auto-start override.

    Temporarily override whether built-in models auto-start on container restart.
    This setting is ephemeral (stored in Redis) and expires after TTL.

    **Access:** Requires `admin:all` scope.

    **Graceful degradation:**
    - Returns 200 even if Redis is unavailable (check `error` field)
    - Returns 200 with `allowed: false` if feature is disabled via config

    **Mirrors:** `POST /v1/internal/ops/auto-start-override`
    """,
    responses={
        200: {
            "description": "Override applied successfully (or feature disabled)",
            "content": {
                "application/json": {
                    "examples": {
                        "success": {
                            "summary": "Success",
                            "value": {"allowed": True, "enabled": True, "ttl_seconds": 600},
                        },
                        "disabled": {
                            "summary": "Feature disabled",
                            "value": {"allowed": False, "enabled": False, "ttl_seconds": 0},
                        },
                        "cache_error": {
                            "summary": "Redis unavailable",
                            "value": {"allowed": True, "enabled": True, "ttl_seconds": 0, "error": "cache_unavailable"},
                        },
                    }
                }
            },
        },
        403: {"description": "Forbidden - requires admin:all scope"},
        422: {"description": "Validation error"},
    },
)
async def admin_auto_start_override(
    request: AutoStartOverrideRequest, principal: Annotated[Principal, Depends(require_admin())]
) -> AutoStartOverrideResponse:
    """
    Admin endpoint to override auto-start behavior.

    Calls the same storage layer as /internal/ops/auto-start-override.
    """
    actor_sub = principal.sub

    # Check if feature is enabled via config
    if not settings.INTERNAL_UI_OVERRIDE_ALLOWED:
        logger.info(
            f"Auto-start override disabled by config (actor: {actor_sub})",
            extra={"actor": actor_sub, "requested_enabled": request.enabled},
        )
        return AutoStartOverrideResponse(allowed=False, enabled=False, ttl_seconds=0)

    # Write to Redis with TTL
    ttl_seconds = settings.INTERNAL_UI_OVERRIDE_TTL_SECONDS
    result = await _write_override_to_redis(request.enabled, ttl_seconds)

    # Audit the operation
    _audit_operation(
        actor_sub=actor_sub,
        kind="auto_start_override",
        enabled=request.enabled,
        note=request.note,
        data={"ttl_seconds": result["ttl_seconds"], "route": "/admin/ops/auto-start-override"},
    )

    logger.info(
        f"Auto-start override set to {request.enabled} by admin {actor_sub}",
        extra={
            "actor": actor_sub,
            "enabled": request.enabled,
            "ttl_seconds": result["ttl_seconds"],
            "error": result.get("error"),
        },
    )

    return AutoStartOverrideResponse(**result)


@router.get(
    "/preview-staged",
    response_model=PreviewStagedResponse,
    status_code=status.HTTP_200_OK,
    summary="Preview staged manifests (Admin)",
    description="""
    Admin-facing proxy for internal preview-staged.

    Returns a preview of which model manifests would be deployed if the container
    restarted right now, taking into account the current auto-start override setting.

    **Access:** Requires `admin:all` scope.

    **Caching:** Results cached for 45 seconds. Use `force_refresh=true` to bypass cache.

    **Mirrors:** `GET /v1/internal/ops/preview-staged`
    """,
    responses={
        200: {
            "description": "Preview of staged manifests",
            "content": {
                "application/json": {
                    "example": {
                        "items": [{"name": "llama3.2", "version": "3b", "auto_start": True, "source": "builtin"}],
                        "count": 1,
                        "override_active": True,
                        "timestamp": "2025-10-22T10:30:00Z",
                    }
                }
            },
        },
        403: {"description": "Forbidden - requires admin:all scope"},
    },
)
async def admin_preview_staged(
    principal: Annotated[Principal, Depends(require_admin())],
    force_refresh: Annotated[bool, Query(description="Bypass cache")] = False,
) -> PreviewStagedResponse:
    """
    Admin endpoint to preview staged manifests.

    Reads from the same Redis keys as /internal/ops/preview-staged.
    """
    # TODO: Implement actual manifest reading logic
    # For now, return a placeholder that shows override state

    override_active, _override_data = await _read_override_from_redis()

    # Placeholder: in real implementation, read from run/manifests/builtin/*.yml
    items = [PreviewStagedManifest(name="llama3.2", version="3b", auto_start=override_active, source="builtin")]

    logger.info(
        f"Preview staged requested by admin {principal.sub}",
        extra={
            "actor": principal.sub,
            "force_refresh": force_refresh,
            "override_active": override_active,
            "count": len(items),
        },
    )

    return PreviewStagedResponse(
        items=items, count=len(items), override_active=override_active, timestamp=datetime.now(UTC)
    )
