"""
Builtins Manifests endpoints (admin-only).

Mounted under /admin/models by the application.

Endpoints:
- GET    /admin/models/manifests/builtins           -> list built-in manifests
- POST   /admin/models/manifests/builtins/staged    -> stage remote manifest (fetch + validate)
- POST   /admin/models/manifests/builtins/activations -> activate latest staged manifest
- POST   /admin/models/manifests/builtins/rollbacks  -> rollback to previous active manifest
- GET    /admin/models/manifests/builtins/history   -> list activation history

All endpoints require admin:all permission (RBAC enforced).
Implements ETag/304 for list + history endpoints.
Idempotency-Key support for stage/activate/rollback operations (24h replay protection).
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from db.postgres_control.repositories import manifest_repo, model_instance_repo, provider_repo
from db.redis_cache.client import idem_get, idem_set
from src.config import settings
from src.provenance import record_provenance
from src.schemas.auth import UserInfo
from src.routers.auth import get_current_user
from src.security.perm import require_perms

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/models/manifests/builtins", tags=["models-manifests-builtins"])

# ========== Request/Response Models ==========


class StageManifestRequest(BaseModel):
    """Request to stage a remote manifest or inline content."""

    url: str | None = Field(
        None, description="HTTPS URL to fetch manifest JSON from (mutually exclusive with inline)"
    )
    inline: dict[str, Any] | None = Field(None, description="Inline manifest content (mutually exclusive with url)")

    @model_validator(mode="after")
    def validate_exactly_one(self):
        if not self.url and not self.inline:
            raise ValueError("Either 'url' or 'inline' must be provided")
        if self.url and self.inline:
            raise ValueError("Only one of 'url' or 'inline' can be provided")
        return self


class StageManifestResponse(BaseModel):
    """Response for staging operation."""

    ok: bool = True
    message: str
    details: dict[str, Any]
    trace_id: str | None = None
    event_id: str | None = None


class ActivateManifestRequest(BaseModel):
    """Request to activate latest staged manifest."""

    reason: str | None = Field(None, description="Optional reason for activation")


class ActivateManifestResponse(BaseModel):
    """Response for activation operation."""

    ok: bool = True
    message: str
    details: dict[str, Any]
    trace_id: str | None = None
    event_id: str | None = None


class RollbackManifestRequest(BaseModel):
    """Request to rollback to previous manifest."""

    reason: str | None = Field(None, description="Optional reason for rollback")


class RollbackManifestResponse(BaseModel):
    """Response for rollback operation."""

    ok: bool = True
    message: str
    details: dict[str, Any]
    trace_id: str | None = None
    event_id: str | None = None


class ListBuiltinsResponse(BaseModel):
    """Response for list builtins.

    Uses standard format {items, total, etag, next_page_token}.
    Maintains backward compatibility via aliases (manifests -> items, count -> total).
    """

    items: list[dict[str, Any]] = Field(..., description="List of manifest objects")
    total: int = Field(..., description="Total number of manifests")
    etag: str = Field(..., description="ETag for cache validation")
    next_page_token: str | None = Field(None, description="Pagination token (future use)")

    # Backward compatibility aliases
    @property
    def manifests(self) -> list[dict[str, Any]]:
        """Deprecated: Use 'items' instead."""
        return self.items

    @property
    def count(self) -> int:
        """Deprecated: Use 'total' instead."""
        return self.total

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "items": [{"id": "uuid", "version": "1.0.0", "state": "active"}],
                "total": 1,
                "etag": "abc123def456",
                "next_page_token": None,
            }
        }
    )


class ListHistoryResponse(BaseModel):
    """Response for activation history.

    Uses standard format {items, total, etag, next_page_token}.
    Maintains backward compatibility via aliases (activations -> items, count -> total).
    """

    items: list[dict[str, Any]] = Field(..., description="List of activation records")
    total: int = Field(..., description="Total number of activations")
    etag: str = Field(..., description="ETag for cache validation")
    next_page_token: str | None = Field(None, description="Pagination token (future use)")

    # Backward compatibility aliases
    @property
    def activations(self) -> list[dict[str, Any]]:
        """Deprecated: Use 'items' instead."""
        return self.items

    @property
    def count(self) -> int:
        """Deprecated: Use 'total' instead."""
        return self.total

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "items": [{"id": "uuid", "manifest_id": "uuid", "activated_at": "2025-10-13T20:00:00Z"}],
                "total": 10,
                "etag": "xyz789abc123",
                "next_page_token": None,
            }
        }
    )


# ========== Helper Functions ==========


def _egress_allowed(url: str) -> bool:
    """Check if egress to URL is allowed per EGRESS_ALLOWLIST."""
    if not url:
        return False

    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()

    if not host:
        return False

    allow_list = settings.EGRESS_ALLOWLIST
    if not allow_list:
        return True  # No allowlist = allow all

    # Check if host matches any allowed patterns
    for pattern in allow_list:
        if pattern == "*":
            return True
        if host == pattern.lower() or host.endswith(f".{pattern.lower()}"):
            return True

    return False


def _fetch_manifest(url: str) -> dict[str, Any]:
    """Fetch manifest JSON from remote URL with validation."""
    # Validate URL scheme
    if not url.startswith("https://"):
        raise ValueError("Only HTTPS URLs are allowed for manifest fetching")

    # Check egress policy
    if not _egress_allowed(url):
        raise ValueError(f"Egress to {urlparse(url).netloc} not allowed by EGRESS_ALLOWLIST")

    # Fetch with timeout
    try:
        timeout = httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0)
        resp = httpx.get(url, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()

        # Parse JSON
        content = resp.json()

        # Basic validation: must be a list/array of model definitions
        if not isinstance(content, (list, dict)):
            raise ValueError("Manifest must be a JSON array or object")

        return content

    except httpx.HTTPStatusError as exc:
        raise ValueError(f"Failed to fetch manifest: HTTP {exc.response.status_code}")
    except httpx.RequestError as exc:
        raise ValueError(f"Network error fetching manifest: {exc}")
    except json.JSONDecodeError:
        raise ValueError("Manifest is not valid JSON")


def _compute_content_hash(content: Any) -> str:
    """Compute SHA256 hash of manifest content (deterministic)."""
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _extract_version(content: Any) -> str | None:
    """Attempt to extract version tag from manifest content."""
    # If content is a dict with 'version' key, use it
    if isinstance(content, dict) and "version" in content:
        return str(content["version"])

    # If content is a list, check first item for version
    if isinstance(content, list) and len(content) > 0 and isinstance(content[0], dict):
        if "version" in content[0]:
            return str(content[0]["version"])

    return None


def _generate_trace_id() -> str:
    """Generate trace ID for correlation."""
    return f"trace-{uuid.uuid4().hex[:16]}"


def _generate_event_id() -> str:
    """Generate event ID for provenance."""
    return f"event-{uuid.uuid4().hex[:16]}"


def _add_standard_headers(response: Response, etag: str | None = None):
    """Add standard headers (X-Request-Id, Cache-Control, Vary, ETag)."""
    response.headers["X-Request-Id"] = _generate_trace_id()
    response.headers["Cache-Control"] = "no-cache, must-revalidate"
    response.headers["Vary"] = "Authorization"

    if etag:
        response.headers["ETag"] = f'"{etag}"'


def _check_etag(request: Request, current_etag: str) -> bool:
    """Check If-None-Match header against current ETag. Returns True if match (304)."""
    if_none_match = request.headers.get("If-None-Match", "").strip().strip('"')
    return if_none_match == current_etag


def _check_idempotency(user: UserInfo, idempotency_key: str | None, operation: str) -> dict[str, Any] | None:
    """Check for idempotency replay. Returns cached result if found, None otherwise."""
    if not idempotency_key:
        return None

    # Build cache key: manifests:idemp:{sub}:{key}
    cache_key = f"manifests:idemp:{user.sub}:{idempotency_key}"

    try:
        cached = idem_get(cache_key)
        if cached:
            logger.info(f"manifests.{operation}.replayed", extra={"user": user.sub, "idempotency_key": idempotency_key})
            return cached
    except Exception as exc:
        logger.warning("manifests.idemp.check_failed", extra={"error": str(exc)})

    return None


def _store_idempotency(user: UserInfo, idempotency_key: str | None, result: dict[str, Any], ttl: int = 86400):
    """Store idempotency result for replay protection (24h TTL)."""
    if not idempotency_key:
        return

    cache_key = f"manifests:idemp:{user.sub}:{idempotency_key}"

    try:
        idem_set(cache_key, result, ttl=ttl)
    except Exception as exc:
        logger.warning("manifests.idemp.store_failed", extra={"error": str(exc)})


def _sync_manifest_to_instances(
    manifest: dict[str, Any], actor_sub: str, trace_id: str | None = None
) -> dict[str, Any]:
    """Sync manifest models to model instances.

    When a manifest is activated, this function creates/updates model instances
    for each model in the manifest. This allows the orchestrator to load models
    from the model_instances table.

    Args:
        manifest: The activated manifest with content.models array
        actor_sub: The user sub who activated the manifest
        trace_id: Optional trace ID for audit

    Returns:
        Dict with sync statistics (created, updated, errors)
    """
    stats = {"created": 0, "updated": 0, "skipped": 0, "errors": []}

    # Extract models from manifest content
    content = manifest.get("content", {})
    models = content.get("models", [])

    if not models:
        logger.warning("manifests.sync.no_models", extra={"manifest_id": manifest.get("id")})
        return stats

    logger.info(
        "manifests.sync.starting",
        extra={"manifest_id": manifest.get("id"), "model_count": len(models), "trace_id": trace_id},
    )

    for model in models:
        try:
            model_id = model.get("id")
            model_name = model.get("name") or model_id
            provider_id = model.get("provider")

            if not model_id or not provider_id:
                stats["errors"].append({"model": model_id or "unknown", "error": "Missing id or provider"})
                continue

            # Verify provider exists
            try:
                provider = provider_repo.get_provider(provider_id)
                if not provider:
                    stats["errors"].append({"model": model_id, "error": f"Provider not found: {provider_id}"})
                    continue
            except Exception as exc:
                stats["errors"].append({"model": model_id, "error": f"Provider lookup failed: {exc!s}"})
                continue

            # Create instance name from model_id (normalize to valid identifier)
            instance_name = model_id.replace(":", "-").replace(".", "-").replace("/", "-")

            # Create or update model instance
            try:
                model_instance_repo.create_instance(
                    provider_id=provider_id,
                    instance_name=instance_name,
                    model_id=model_id,
                    tenant_id=None,  # Global instance
                    description=model.get("description"),
                    context_window=model.get("context_window"),
                    modalities=model.get("capabilities"),  # Map capabilities to modalities
                    parameters={
                        "max_tokens": model.get("max_tokens"),
                        "pricing": model.get("pricing"),
                        "manifest_name": model_name,
                    },
                    owner_sub=actor_sub,
                    trace_id=trace_id,
                )

                # create_instance returns existing if name already exists (idempotent)
                # Check if it was newly created or already existed
                stats["created"] += 1

                logger.info(
                    "manifests.sync.instance_created",
                    extra={
                        "instance_name": instance_name,
                        "model_id": model_id,
                        "provider_id": provider_id,
                    },
                )

            except ValueError as exc:
                # Instance already exists
                if "already exists" in str(exc):
                    stats["skipped"] += 1
                    logger.debug("manifests.sync.instance_exists", extra={"instance_name": instance_name})
                else:
                    stats["errors"].append({"model": model_id, "error": str(exc)})

        except Exception as exc:
            stats["errors"].append({"model": model.get("id", "unknown"), "error": str(exc)})
            logger.error("manifests.sync.instance_failed", extra={"model": model.get("id"), "error": str(exc)})

    logger.info(
        "manifests.sync.completed", extra={"manifest_id": manifest.get("id"), "stats": stats, "trace_id": trace_id}
    )

    return stats


# ========== Endpoints ==========


@router.get(
    "",
    response_model=ListBuiltinsResponse,
    summary="List built-in manifests",
    description="Returns all builtin manifests (active + staged + archived) with ETag support for conditional requests.",
    dependencies=[Depends(require_perms("admin:all"))],
)
async def list_builtins(
    request: Request,
    response: Response,
    user: UserInfo = Depends(get_current_user),
):
    """List all builtin manifests (GET /admin/models/manifests/builtins)."""
    try:
        # Get manifests + ETag
        manifests, etag = manifest_repo.list_builtins()

        # Check If-None-Match for 304
        if _check_etag(request, etag):
            _add_standard_headers(response, etag)
            return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=response.headers)

        # Add standard headers
        _add_standard_headers(response, etag)

        logger.info("manifests.list.success", extra={"user": user.sub, "count": len(manifests)})

        return ListBuiltinsResponse(
            items=manifests,
            total=len(manifests),
            etag=etag,
            next_page_token=None,
        )

    except Exception as exc:
        logger.error("manifests.list.failed", extra={"error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail={"type": "internal_error", "message": str(exc)}
        )


@router.post(
    "/staged",
    response_model=StageManifestResponse,
    summary="Stage remote manifest",
    description="Fetch and validate a remote manifest, staging it for later activation. Supports idempotency via Idempotency-Key header.",
    dependencies=[Depends(require_perms("admin:all"))],
)
async def stage_manifest(
    request: Request,
    response: Response,
    payload: StageManifestRequest,
    user: UserInfo = Depends(get_current_user),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    """Stage a remote manifest (POST /admin/models/manifests/builtins/staged)."""
    trace_id = _generate_trace_id()
    event_id = _generate_event_id()

    try:
        # Check idempotency
        if idempotency_key:
            cached = _check_idempotency(user, idempotency_key, "stage")
            if cached:
                response.headers["Idempotency-Replayed"] = "true"
                _add_standard_headers(response)
                return StageManifestResponse(**cached)

        # Get manifest content (from URL or inline)
        if payload.inline:
            content = payload.inline
            source_url = "inline"
        else:
            content = _fetch_manifest(payload.url)
            source_url = payload.url

        # Compute SHA256
        sha256 = _compute_content_hash(content)

        # Extract version (if present)
        version = _extract_version(content)

        # Stage in repository
        manifest = manifest_repo.stage_manifest(
            url=source_url,
            content_json=content,
            sha256=sha256,
            actor_sub=user.sub,
            version=version,
            trace_id=trace_id,
            event_id=event_id,
            idempotency_key=idempotency_key,
        )

        # Record provenance
        record_provenance(
            actor="api",
            action="manifest.staged",
            resource="/admin/models/manifests/builtins/staged",
            input={"source": source_url},
            output={"manifest_id": manifest["id"], "sha256": sha256},
            meta={
                "source_url": source_url,
                "sha256": sha256,
                "version": version,
                "user": user.sub,
            },
            trace_id=trace_id,
            success=True,
        )

        result = {
            "ok": True,
            "message": "Manifest staged successfully",
            "details": {
                "manifest_id": manifest["id"],
                "sha256": sha256,
                "version": version,
                "state": manifest["state"],
            },
            "trace_id": trace_id,
            "event_id": event_id,
        }

        # Store idempotency result
        _store_idempotency(user, idempotency_key, result)

        # Add headers
        _add_standard_headers(response)

        logger.info(
            "manifests.stage.success",
            extra={
                "user": user.sub,
                "manifest_id": manifest["id"],
                "sha256": sha256,
                "trace_id": trace_id,
            },
        )

        return StageManifestResponse(**result)

    except ValueError as exc:
        logger.warning("manifests.stage.validation_failed", extra={"error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail={"type": "validation_error", "message": str(exc)}
        )
    except Exception as exc:
        logger.error("manifests.stage.failed", extra={"error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail={"type": "internal_error", "message": str(exc)}
        )


@router.post(
    "/activations",
    response_model=ActivateManifestResponse,
    summary="Activate latest staged manifest",
    description="Atomically activate the most recent staged manifest, demoting current active to archived. Uses Redis lock for serialization. Supports idempotency.",
    dependencies=[Depends(require_perms("admin:all"))],
)
async def activate_manifest(
    request: Request,
    response: Response,
    payload: ActivateManifestRequest | None = None,
    user: UserInfo = Depends(get_current_user),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    """Activate latest staged manifest (POST /admin/models/manifests/builtins/activations)."""
    trace_id = _generate_trace_id()
    event_id = _generate_event_id()

    # Handle empty body (payload can be None)
    reason = payload.reason if payload else None

    try:
        # Check idempotency
        if idempotency_key:
            cached = _check_idempotency(user, idempotency_key, "activate")
            if cached:
                response.headers["Idempotency-Replayed"] = "true"
                _add_standard_headers(response)
                return ActivateManifestResponse(**cached)

        # Activate in repository (acquires lock, validates, updates state)
        activated, previous = manifest_repo.activate_latest_staged(
            actor_sub=user.sub,
            reason=reason,
            trace_id=trace_id,
            event_id=event_id,
            idempotency_key=idempotency_key,
        )

        # Sync manifest models to model instances (auto-create/update)
        sync_stats = _sync_manifest_to_instances(manifest=activated, actor_sub=user.sub, trace_id=trace_id)

        # Record provenance
        record_provenance(
            actor="api",
            action="manifest.activated",
            resource="/admin/models/manifests/builtins/activations",
            input={"reason": reason},
            output={"manifest_id": activated["id"]},
            meta={
                "previous_manifest_id": previous["id"] if previous else None,
                "reason": reason,
                "user": user.sub,
            },
            trace_id=trace_id,
            success=True,
        )

        result = {
            "ok": True,
            "message": "Manifest activated successfully",
            "details": {
                "active_manifest_id": activated["id"],
                "prev_manifest_id": previous["id"] if previous else None,
                "version": activated.get("version"),
                "sync_stats": sync_stats,  # Include instance sync statistics
            },
            "trace_id": trace_id,
            "event_id": event_id,
        }

        # Store idempotency result
        _store_idempotency(user, idempotency_key, result)

        # Add headers
        _add_standard_headers(response)

        logger.info(
            "manifests.activate.success",
            extra={
                "user": user.sub,
                "manifest_id": activated["id"],
                "previous_id": previous["id"] if previous else None,
                "trace_id": trace_id,
            },
        )

        return ActivateManifestResponse(**result)

    except ValueError as exc:
        logger.warning("manifests.activate.failed", extra={"error": str(exc)})

        # Check for specific error conditions
        if "lock held" in str(exc).lower():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"type": "conflict", "message": str(exc)})
        elif "no staged manifest" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail={"type": "validation_error", "message": str(exc)}
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail={"type": "validation_error", "message": str(exc)}
            )
    except Exception as exc:
        logger.error("manifests.activate.failed", extra={"error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail={"type": "internal_error", "message": str(exc)}
        )


@router.post(
    "/rollbacks",
    response_model=RollbackManifestResponse,
    summary="Rollback to previous active manifest",
    description="Atomically rollback to the previous active manifest, demoting current to archived. Uses Redis lock for serialization. Supports idempotency.",
    dependencies=[Depends(require_perms("admin:all"))],
)
async def rollback_manifest(
    request: Request,
    response: Response,
    payload: RollbackManifestRequest | None = None,
    user: UserInfo = Depends(get_current_user),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    """Rollback to previous manifest (POST /admin/models/manifests/builtins/rollbacks)."""
    trace_id = _generate_trace_id()
    event_id = _generate_event_id()

    # Handle empty body
    reason = payload.reason if payload else None

    try:
        # Check idempotency
        if idempotency_key:
            cached = _check_idempotency(user, idempotency_key, "rollback")
            if cached:
                response.headers["Idempotency-Replayed"] = "true"
                _add_standard_headers(response)
                return RollbackManifestResponse(**cached)

        # Rollback in repository
        restored, rolled_from = manifest_repo.rollback_to_previous(
            actor_sub=user.sub,
            reason=reason,
            trace_id=trace_id,
            event_id=event_id,
            idempotency_key=idempotency_key,
        )

        # Record provenance
        record_provenance(
            actor="api",
            action="manifest.rollback",
            resource="/admin/models/manifests/builtins/rollbacks",
            input={"reason": reason},
            output={"manifest_id": restored["id"]},
            meta={
                "rolled_from_id": rolled_from["id"],
                "reason": reason,
                "user": user.sub,
            },
            trace_id=trace_id,
            success=True,
        )

        result = {
            "ok": True,
            "message": "Manifest rollback completed successfully",
            "details": {
                "active_manifest_id": restored["id"],
                "prev_manifest_id": rolled_from["id"],
                "version": restored.get("version"),
            },
            "trace_id": trace_id,
            "event_id": event_id,
        }

        # Store idempotency result
        _store_idempotency(user, idempotency_key, result)

        # Add headers
        _add_standard_headers(response)

        logger.info(
            "manifests.rollback.success",
            extra={
                "user": user.sub,
                "restored_id": restored["id"],
                "rolled_from_id": rolled_from["id"],
                "trace_id": trace_id,
            },
        )

        return RollbackManifestResponse(**result)

    except ValueError as exc:
        logger.warning("manifests.rollback.failed", extra={"error": str(exc)})

        if "lock held" in str(exc).lower():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"type": "conflict", "message": str(exc)})
        elif "no previous manifest" in str(exc).lower() or "no active manifest" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail={"type": "validation_error", "message": str(exc)}
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail={"type": "validation_error", "message": str(exc)}
            )
    except Exception as exc:
        logger.error("manifests.rollback.failed", extra={"error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail={"type": "internal_error", "message": str(exc)}
        )


@router.get(
    "/history",
    response_model=ListHistoryResponse,
    summary="List activation history",
    description="Returns recent activation/rollback events with ETag support for conditional requests.",
    dependencies=[Depends(require_perms("admin:all"))],
)
async def list_history(
    request: Request,
    response: Response,
    user: UserInfo = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=500, description="Maximum number of activations to return"),
):
    """List activation history (GET /admin/models/manifests/builtins/history)."""
    try:
        # Get history + ETag
        activations, etag = manifest_repo.list_history(limit=limit)

        # Check If-None-Match for 304
        if _check_etag(request, etag):
            _add_standard_headers(response, etag)
            return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=response.headers)

        # Add standard headers
        _add_standard_headers(response, etag)

        logger.info("manifests.history.success", extra={"user": user.sub, "count": len(activations)})

        return ListHistoryResponse(
            items=activations,
            total=len(activations),
            etag=etag,
            next_page_token=None,
        )

    except Exception as exc:
        logger.error("manifests.history.failed", extra={"error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail={"type": "internal_error", "message": str(exc)}
        )
