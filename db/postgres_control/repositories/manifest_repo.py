"""PostgreSQL repository for Builtins Manifests management (authoritative source).

This module provides operations for builtin model manifests with:
- PostgreSQL as authoritative source (all writes go to Postgres first)
- Redis as cache layer (TTLs, invalidated on writes)
- Content-based idempotency via SHA256
- Activation/rollback with history tracking
- Audit event logging for all mutations
- Redis locks for atomic activation/rollback

Storage layers:
1. PostgreSQL: builtins_manifests, builtins_activations, builtins_staging_jobs, builtins_manifest_audit
2. Redis: Cache keys with TTLs (manifests:builtins:active, manifests:builtins:list, manifests:builtins:history, etc.)

State machine:
- staged → active (on activation)
- active → archived (when new manifest activated)
- archived → active (on rollback)
"""

from __future__ import annotations

import hashlib
import json
import logging
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.postgres_control.database import get_db
from db.postgres_control.models.manifest import (
    BuiltinsActivation,
    BuiltinsManifest,
    BuiltinsManifestAudit,
    BuiltinsStagingJob,
)
from db.redis_cache.client import (
    cache_delete,
    cache_get_json,
    cache_set_json,
    get_redis,
    redis_available,
)

logger = logging.getLogger(__name__)

# Prometheus metrics (initialized lazily)
_METRICS_INITIALIZED = False
MANIFEST_STAGED_COUNTER = None
MANIFEST_ACTIVATED_COUNTER = None
MANIFEST_ROLLBACK_COUNTER = None
BUILTINS_ACTIVE_VERSION_GAUGE = None


def _init_metrics():
    """Initialize Prometheus metrics for manifests (lazy initialization)."""
    global _METRICS_INITIALIZED, MANIFEST_STAGED_COUNTER, MANIFEST_ACTIVATED_COUNTER, MANIFEST_ROLLBACK_COUNTER, BUILTINS_ACTIVE_VERSION_GAUGE

    if _METRICS_INITIALIZED:
        return

    try:
        from prometheus_client import Counter, Gauge

        MANIFEST_STAGED_COUNTER = Counter(
            "manifest_staged_total", "Total number of manifests staged", ["result"]  # success, error
        )

        MANIFEST_ACTIVATED_COUNTER = Counter(
            "manifest_activated_total", "Total number of manifest activations", ["result"]  # success, error
        )

        MANIFEST_ROLLBACK_COUNTER = Counter(
            "manifest_rollback_total", "Total number of manifest rollbacks", ["result"]  # success, error
        )

        BUILTINS_ACTIVE_VERSION_GAUGE = Gauge(
            "builtins_active_version_info",
            "Currently active builtins manifest version",
            ["version", "manifest_id", "sha256"],
        )

        _METRICS_INITIALIZED = True
        logger.info("manifest_repo.metrics.initialized")

    except ImportError:
        logger.warning("manifest_repo.metrics.unavailable - prometheus_client not installed")
        _METRICS_INITIALIZED = True  # Don't retry


# Initialize metrics on module load
_init_metrics()

# Redis key templates
REDIS_MANIFEST_ACTIVE = "manifests:builtins:active"
REDIS_MANIFEST_LIST = "manifests:builtins:list"
REDIS_MANIFEST_HISTORY = "manifests:builtins:history"
REDIS_MANIFEST_STAGED = "manifests:builtins:staged:{}"  # sha256
REDIS_MANIFEST_IDEMP = "manifests:idemp:{}:{}"  # owner_sub:key
REDIS_MANIFEST_LOCK_ACTIVATE = "manifests:locks:activate"

# Cache TTLs (seconds)
TTL_ACTIVE = None  # No expiry for active manifest
TTL_LIST = 60  # 1 minute
TTL_HISTORY = 60  # 1 minute
TTL_STAGED = 600  # 10 minutes
TTL_IDEMP = 86400  # 24 hours
TTL_LOCK = 30  # 30 seconds


def _compute_content_hash(content: Any) -> str:
    """Compute SHA256 hash of manifest content (deterministic JSON serialization)."""
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _compute_etag(manifest_id: str, updated_at: datetime) -> str:
    """Compute ETag for a manifest."""
    ts = int(updated_at.timestamp())
    return hashlib.sha256(f"{manifest_id}:{ts}".encode()).hexdigest()[:16]


def _compute_list_etag(manifests: list[dict]) -> str:
    """Compute ETag for list of manifests."""
    if not manifests:
        return hashlib.sha256(b"empty").hexdigest()[:16]

    # Use count + latest updated_at + concatenated IDs
    count = len(manifests)

    # Parse ISO format strings back to datetime if necessary
    def parse_timestamp(m):
        updated = m.get("updated_at")
        if updated:
            if isinstance(updated, str):
                return datetime.fromisoformat(updated.replace("Z", "+00:00"))
            return updated
        return datetime.min.replace(tzinfo=UTC)

    latest = max((parse_timestamp(m) for m in manifests), default=datetime.min.replace(tzinfo=UTC))
    ids = sorted(str(m.get("id", "")) for m in manifests)

    ts = int(latest.timestamp()) if latest != datetime.min.replace(tzinfo=UTC) else 0
    combined = f"{count}:{ts}:{':'.join(ids)}"
    return hashlib.sha256(combined.encode()).hexdigest()[:16]


def _compute_history_etag(activations: list[dict]) -> str:
    """Compute ETag for activation history."""
    if not activations:
        return hashlib.sha256(b"empty").hexdigest()[:16]

    count = len(activations)

    # Parse ISO format strings back to datetime if necessary
    def parse_timestamp(a):
        activated = a.get("activated_at")
        if activated:
            if isinstance(activated, str):
                return datetime.fromisoformat(activated.replace("Z", "+00:00"))
            return activated
        return datetime.min.replace(tzinfo=UTC)

    latest = max((parse_timestamp(a) for a in activations), default=datetime.min.replace(tzinfo=UTC))
    ids = [str(a.get("id", "")) for a in activations[:10]]  # Top 10 IDs

    ts = int(latest.timestamp()) if latest != datetime.min.replace(tzinfo=UTC) else 0
    combined = f"{count}:{ts}:{':'.join(ids)}"
    return hashlib.sha256(combined.encode()).hexdigest()[:16]


def _redis_invalidate_manifest(manifest_id: str | None = None):
    """Invalidate Redis caches for manifests (called on stage/activate/rollback/delete)."""
    if not redis_available():
        return

    try:
        get_redis()

        # Invalidate list and history (always)
        cache_delete(REDIS_MANIFEST_LIST)
        cache_delete(REDIS_MANIFEST_HISTORY)

        # Invalidate specific staged snapshot if manifest_id known
        if manifest_id:
            # Need to find sha256 to clear staged cache
            with suppress(Exception):
                cache_delete("manifests:builtins:staged:*")  # Clear all staged

        logger.debug("manifest_repo.cache.invalidated", extra={"manifest_id": manifest_id})
    except Exception as exc:
        logger.warning("manifest_repo.cache.invalidate_failed", extra={"error": str(exc)})


def _redis_invalidate_active():
    """Invalidate active manifest cache (called on activate/rollback)."""
    if not redis_available():
        return

    try:
        cache_delete(REDIS_MANIFEST_ACTIVE)
        logger.debug("manifest_repo.cache.active_invalidated")
    except Exception as exc:
        logger.warning("manifest_repo.cache.active_invalidate_failed", extra={"error": str(exc)})


def _acquire_activation_lock() -> bool:
    """Acquire Redis lock for activation/rollback (returns True if acquired, False if already locked)."""
    if not redis_available():
        return True  # No Redis, proceed without lock

    try:
        r = get_redis()
        # SET NX (only set if not exists) with TTL
        acquired = r.set(REDIS_MANIFEST_LOCK_ACTIVATE, "1", nx=True, ex=TTL_LOCK)
        return bool(acquired)
    except Exception as exc:
        logger.warning("manifest_repo.lock.acquire_failed", extra={"error": str(exc)})
        return True  # Proceed on Redis failure


def _release_activation_lock():
    """Release activation/rollback lock."""
    if not redis_available():
        return

    try:
        cache_delete(REDIS_MANIFEST_LOCK_ACTIVATE)
    except Exception as exc:
        logger.warning("manifest_repo.lock.release_failed", extra={"error": str(exc)})


def _audit_event(
    db: Session,
    action: str,
    actor_sub: str,
    manifest_id: UUID | None = None,
    details: dict | None = None,
    trace_id: str | None = None,
    event_id: str | None = None,
):
    """Write audit event to builtins_manifest_audit."""
    try:
        audit = BuiltinsManifestAudit(
            manifest_id=manifest_id,
            action=action,
            details_json=details or {},
            actor_sub=actor_sub,
            trace_id=trace_id,
            event_id=event_id,
        )
        db.add(audit)
        db.flush()

        logger.info(
            f"manifest_audit.{action}",
            extra={
                "manifest_id": str(manifest_id) if manifest_id else None,
                "actor": actor_sub,
                "trace_id": trace_id,
                "event_id": event_id,
            },
        )
    except Exception as exc:
        logger.error("manifest_audit.failed", extra={"action": action, "error": str(exc)})


def stage_manifest(
    url: str,
    content_json: Any,
    sha256: str,
    actor_sub: str,
    version: str | None = None,
    trace_id: str | None = None,
    event_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Stage a new manifest (or return existing staged manifest if sha256 matches).

    Args:
        url: Source URL from which manifest was fetched
        content_json: Full manifest content (array of model definitions)
        sha256: SHA256 hash of content (for content-based idempotency)
        actor_sub: Subject ID of user staging the manifest
        version: Optional version tag extracted from manifest
        trace_id: Optional trace ID for correlation
        event_id: Optional event ID for provenance
        idempotency_key: Optional idempotency key for staging job tracking

    Returns:
        Dict with manifest details (id, sha256, state, etag, created_at, etc.)
    """
    db: Session = next(get_db())

    try:
        # Check if manifest with this sha256 already exists (content-based idempotency)
        stmt = select(BuiltinsManifest).where(BuiltinsManifest.sha256 == sha256)
        existing = db.execute(stmt).scalar_one_or_none()

        if existing:
            logger.info(
                "manifest_repo.stage.existing",
                extra={"manifest_id": str(existing.id), "sha256": sha256, "state": existing.state},
            )

            # Record idempotency job if key provided
            if idempotency_key:
                _record_staging_job(
                    db=db,
                    idempotency_key=idempotency_key,
                    source_url=url,
                    sha256=sha256,
                    actor_sub=actor_sub,
                    status="ok",
                )

            return _manifest_to_dict(existing)

        # Create new staged manifest
        now = datetime.now(UTC)

        # Compute initial ETag (will use actual ID after insert)
        etag = hashlib.sha256(f"{sha256}:{int(now.timestamp())}".encode()).hexdigest()[:16]

        new_manifest = BuiltinsManifest(
            source_url=url,
            content_json=content_json,
            sha256=sha256,
            version=version,
            state="staged",
            created_by_sub=actor_sub,
            etag=etag,
        )

        db.add(new_manifest)
        db.flush()  # Get ID

        # Update ETag with actual ID
        new_manifest.etag = _compute_etag(str(new_manifest.id), new_manifest.updated_at)

        # Record staging job if idempotency_key provided
        if idempotency_key:
            _record_staging_job(
                db=db,
                idempotency_key=idempotency_key,
                source_url=url,
                sha256=sha256,
                actor_sub=actor_sub,
                status="ok",
            )

        # Audit event
        _audit_event(
            db=db,
            action="stage",
            actor_sub=actor_sub,
            manifest_id=new_manifest.id,
            details={"source_url": url, "sha256": sha256, "version": version},
            trace_id=trace_id,
            event_id=event_id,
        )

        db.commit()

        # Invalidate list cache
        _redis_invalidate_manifest(str(new_manifest.id))

        # Cache staged snapshot
        if redis_available():
            try:
                cache_set_json(
                    REDIS_MANIFEST_STAGED.format(sha256),
                    _manifest_to_dict(new_manifest),
                    ttl=TTL_STAGED,
                )
            except Exception as exc:
                logger.warning("manifest_repo.cache.staged.failed", extra={"error": str(exc)})

        logger.info(
            "manifest_repo.stage.created",
            extra={"manifest_id": str(new_manifest.id), "sha256": sha256, "version": version},
        )

        # Increment metrics
        if MANIFEST_STAGED_COUNTER:
            MANIFEST_STAGED_COUNTER.labels(result="success").inc()

        return _manifest_to_dict(new_manifest)

    except IntegrityError as exc:
        db.rollback()
        if MANIFEST_STAGED_COUNTER:
            MANIFEST_STAGED_COUNTER.labels(result="error").inc()
        logger.error("manifest_repo.stage.integrity_error", extra={"error": str(exc)})
        raise ValueError(f"Integrity constraint violated: {exc}")
    except Exception as exc:
        db.rollback()
        if MANIFEST_STAGED_COUNTER:
            MANIFEST_STAGED_COUNTER.labels(result="error").inc()
        logger.error("manifest_repo.stage.failed", extra={"error": str(exc)})
        raise


def _record_staging_job(
    db: Session,
    idempotency_key: str,
    source_url: str,
    actor_sub: str,
    status: str,
    sha256: str | None = None,
    error_json: dict | None = None,
) -> UUID:
    """Record a staging job for idempotency tracking."""
    try:
        # Check for existing job with same user + key
        stmt = select(BuiltinsStagingJob).where(
            and_(
                BuiltinsStagingJob.created_by_sub == actor_sub,
                BuiltinsStagingJob.idempotency_key == idempotency_key,
            )
        )
        existing = db.execute(stmt).scalar_one_or_none()

        if existing:
            return existing.id

        job = BuiltinsStagingJob(
            idempotency_key=idempotency_key,
            source_url=source_url,
            sha256=sha256,
            created_by_sub=actor_sub,
            status=status,
            error_json=error_json,
        )
        db.add(job)
        db.flush()

        logger.debug("manifest_repo.staging_job.recorded", extra={"job_id": str(job.id)})
        return job.id

    except IntegrityError:
        # Race condition - another request created the job
        db.rollback()
        stmt = select(BuiltinsStagingJob).where(
            and_(
                BuiltinsStagingJob.created_by_sub == actor_sub,
                BuiltinsStagingJob.idempotency_key == idempotency_key,
            )
        )
        existing = db.execute(stmt).scalar_one_or_none()
        return existing.id if existing else None


def activate_latest_staged(
    actor_sub: str,
    reason: str | None = None,
    trace_id: str | None = None,
    event_id: str | None = None,
    idempotency_key: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Activate the most recent staged manifest (atomic operation).

    Args:
        actor_sub: Subject ID of user activating the manifest
        reason: Optional reason for activation
        trace_id: Optional trace ID for correlation
        event_id: Optional event ID for provenance
        idempotency_key: Optional idempotency key for replay protection

    Returns:
        Tuple of (activated_manifest, previous_active_manifest_or_none)

    Raises:
        ValueError: If no staged manifest found or activation lock held
    """
    # Check idempotency first (before acquiring lock)
    if idempotency_key and redis_available():
        try:
            cache_key = REDIS_MANIFEST_IDEMP.format(actor_sub, idempotency_key)
            cached = cache_get_json(cache_key)
            if cached:
                logger.info("manifest_repo.activate.replayed", extra={"idempotency_key": idempotency_key})
                return cached.get("activated"), cached.get("previous")
        except Exception as exc:
            logger.warning("manifest_repo.idemp.check_failed", extra={"error": str(exc)})

    # Acquire activation lock
    if not _acquire_activation_lock():
        raise ValueError("Activation already in progress (lock held)")

    db: Session = next(get_db())

    try:
        # Find most recent staged manifest
        stmt = (
            select(BuiltinsManifest)
            .where(BuiltinsManifest.state == "staged")
            .order_by(desc(BuiltinsManifest.created_at))
            .limit(1)
        )
        staged = db.execute(stmt).scalar_one_or_none()

        if not staged:
            raise ValueError("No staged manifest available for activation")

        # Find currently active manifest (if any)
        stmt_active = select(BuiltinsManifest).where(BuiltinsManifest.state == "active")
        current_active = db.execute(stmt_active).scalar_one_or_none()

        previous_dict = _manifest_to_dict(current_active) if current_active else None

        # Atomically update states
        now = datetime.now(UTC)

        if current_active:
            current_active.state = "archived"
            current_active.updated_at = now

        staged.state = "active"
        staged.activated_at = now
        staged.updated_at = now
        staged.etag = _compute_etag(str(staged.id), now)

        # Record activation history
        activation = BuiltinsActivation(
            manifest_id=staged.id,
            activated_by_sub=actor_sub,
            reason=reason,
            previous_manifest_id=current_active.id if current_active else None,
            trace_id=trace_id,
            event_id=event_id,
        )
        db.add(activation)
        db.flush()

        # Audit event
        _audit_event(
            db=db,
            action="activate",
            actor_sub=actor_sub,
            manifest_id=staged.id,
            details={
                "previous_manifest_id": str(current_active.id) if current_active else None,
                "activation_id": str(activation.id),
                "reason": reason,
            },
            trace_id=trace_id,
            event_id=event_id,
        )

        db.commit()

        activated_dict = _manifest_to_dict(staged)

        # Cache idempotency result
        if idempotency_key and redis_available():
            try:
                cache_key = REDIS_MANIFEST_IDEMP.format(actor_sub, idempotency_key)
                cache_set_json(
                    cache_key,
                    {"activated": activated_dict, "previous": previous_dict},
                    ttl=TTL_IDEMP,
                )
            except Exception as exc:
                logger.warning("manifest_repo.idemp.cache_failed", extra={"error": str(exc)})

        # Invalidate caches
        _redis_invalidate_active()
        _redis_invalidate_manifest(str(staged.id))

        # Cache active manifest
        if redis_available():
            try:
                cache_set_json(REDIS_MANIFEST_ACTIVE, activated_dict, ttl=TTL_ACTIVE)
            except Exception as exc:
                logger.warning("manifest_repo.cache.active.failed", extra={"error": str(exc)})

        logger.info(
            "manifest_repo.activate.success",
            extra={
                "manifest_id": str(staged.id),
                "previous_id": str(current_active.id) if current_active else None,
                "activation_id": str(activation.id),
            },
        )

        # Increment metrics
        if MANIFEST_ACTIVATED_COUNTER:
            MANIFEST_ACTIVATED_COUNTER.labels(result="success").inc()

        # Update active version gauge
        if BUILTINS_ACTIVE_VERSION_GAUGE:
            # Clear previous labels
            BUILTINS_ACTIVE_VERSION_GAUGE.clear()
            # Set new version info
            BUILTINS_ACTIVE_VERSION_GAUGE.labels(
                version=activated_dict.get("version", "unknown"),
                manifest_id=str(staged.id),
                sha256=activated_dict.get("sha256", ""),
            ).set(1)

        return activated_dict, previous_dict

    except Exception as exc:
        db.rollback()
        if MANIFEST_ACTIVATED_COUNTER:
            MANIFEST_ACTIVATED_COUNTER.labels(result="error").inc()
        logger.error("manifest_repo.activate.failed", extra={"error": str(exc)})
        raise
    finally:
        _release_activation_lock()


def rollback_to_previous(
    actor_sub: str,
    reason: str | None = None,
    trace_id: str | None = None,
    event_id: str | None = None,
    idempotency_key: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Rollback to the previous active manifest.

    Args:
        actor_sub: Subject ID of user performing rollback
        reason: Optional reason for rollback
        trace_id: Optional trace ID for correlation
        event_id: Optional event ID for provenance
        idempotency_key: Optional idempotency key for replay protection

    Returns:
        Tuple of (restored_manifest, rolled_from_manifest)

    Raises:
        ValueError: If no previous activation found or rollback lock held
    """
    # Check idempotency first
    if idempotency_key and redis_available():
        try:
            cache_key = REDIS_MANIFEST_IDEMP.format(actor_sub, idempotency_key)
            cached = cache_get_json(cache_key)
            if cached:
                logger.info("manifest_repo.rollback.replayed", extra={"idempotency_key": idempotency_key})
                return cached.get("restored"), cached.get("rolled_from")
        except Exception as exc:
            logger.warning("manifest_repo.idemp.check_failed", extra={"error": str(exc)})

    # Acquire lock
    if not _acquire_activation_lock():
        raise ValueError("Rollback already in progress (lock held)")

    db: Session = next(get_db())

    try:
        # Find current active manifest
        stmt_active = select(BuiltinsManifest).where(BuiltinsManifest.state == "active")
        current_active = db.execute(stmt_active).scalar_one_or_none()

        if not current_active:
            raise ValueError("No active manifest to rollback from")

        # Find previous activation
        stmt_prev = (
            select(BuiltinsActivation)
            .where(BuiltinsActivation.manifest_id == current_active.id)
            .order_by(desc(BuiltinsActivation.activated_at))
            .limit(1)
        )
        last_activation = db.execute(stmt_prev).scalar_one_or_none()

        if not last_activation or not last_activation.previous_manifest_id:
            raise ValueError("No previous manifest to rollback to")

        # Get previous manifest
        stmt_restore = select(BuiltinsManifest).where(BuiltinsManifest.id == last_activation.previous_manifest_id)
        previous_manifest = db.execute(stmt_restore).scalar_one_or_none()

        if not previous_manifest:
            raise ValueError("Previous manifest not found in database")

        # Atomically update states
        now = datetime.now(UTC)

        current_active.state = "archived"
        current_active.updated_at = now

        previous_manifest.state = "active"
        previous_manifest.activated_at = now
        previous_manifest.updated_at = now
        previous_manifest.etag = _compute_etag(str(previous_manifest.id), now)

        # Record rollback as activation
        activation = BuiltinsActivation(
            manifest_id=previous_manifest.id,
            activated_by_sub=actor_sub,
            reason=f"Rollback: {reason}" if reason else "Rollback",
            previous_manifest_id=current_active.id,
            trace_id=trace_id,
            event_id=event_id,
        )
        db.add(activation)
        db.flush()

        # Audit event
        _audit_event(
            db=db,
            action="rollback",
            actor_sub=actor_sub,
            manifest_id=previous_manifest.id,
            details={
                "rolled_from_id": str(current_active.id),
                "restored_to_id": str(previous_manifest.id),
                "activation_id": str(activation.id),
                "reason": reason,
            },
            trace_id=trace_id,
            event_id=event_id,
        )

        db.commit()

        restored_dict = _manifest_to_dict(previous_manifest)
        rolled_from_dict = _manifest_to_dict(current_active)

        # Cache idempotency result
        if idempotency_key and redis_available():
            try:
                cache_key = REDIS_MANIFEST_IDEMP.format(actor_sub, idempotency_key)
                cache_set_json(
                    cache_key,
                    {"restored": restored_dict, "rolled_from": rolled_from_dict},
                    ttl=TTL_IDEMP,
                )
            except Exception as exc:
                logger.warning("manifest_repo.idemp.cache_failed", extra={"error": str(exc)})

        # Invalidate caches
        _redis_invalidate_active()
        _redis_invalidate_manifest(str(previous_manifest.id))

        # Cache restored active manifest
        if redis_available():
            try:
                cache_set_json(REDIS_MANIFEST_ACTIVE, restored_dict, ttl=TTL_ACTIVE)
            except Exception as exc:
                logger.warning("manifest_repo.cache.active.failed", extra={"error": str(exc)})

        logger.info(
            "manifest_repo.rollback.success",
            extra={
                "restored_id": str(previous_manifest.id),
                "rolled_from_id": str(current_active.id),
                "activation_id": str(activation.id),
            },
        )

        # Increment metrics
        if MANIFEST_ROLLBACK_COUNTER:
            MANIFEST_ROLLBACK_COUNTER.labels(result="success").inc()

        # Update active version gauge
        if BUILTINS_ACTIVE_VERSION_GAUGE:
            # Clear previous labels
            BUILTINS_ACTIVE_VERSION_GAUGE.clear()
            # Set restored version info
            BUILTINS_ACTIVE_VERSION_GAUGE.labels(
                version=restored_dict.get("version", "unknown"),
                manifest_id=str(previous_manifest.id),
                sha256=restored_dict.get("sha256", ""),
            ).set(1)

        return restored_dict, rolled_from_dict

    except Exception as exc:
        db.rollback()
        if MANIFEST_ROLLBACK_COUNTER:
            MANIFEST_ROLLBACK_COUNTER.labels(result="error").inc()
        logger.error("manifest_repo.rollback.failed", extra={"error": str(exc)})
        raise
    finally:
        _release_activation_lock()


def list_builtins() -> tuple[list[dict[str, Any]], str]:
    """List all builtin manifests (active + staged + archived).

    Returns:
        Tuple of (manifests_list, collection_etag)
    """
    # Try cache first
    if redis_available():
        try:
            cached = cache_get_json(REDIS_MANIFEST_LIST)
            if cached:
                logger.debug("manifest_repo.list.cache_hit")
                return cached.get("manifests", []), cached.get("etag", "")
        except Exception as exc:
            logger.warning("manifest_repo.list.cache_failed", extra={"error": str(exc)})

    db: Session = next(get_db())

    try:
        # Get all manifests, ordered by state priority then created_at
        stmt = select(BuiltinsManifest).order_by(
            # Active first, then staged, then archived
            sa.case(
                (BuiltinsManifest.state == "active", 1),
                (BuiltinsManifest.state == "staged", 2),
                (BuiltinsManifest.state == "archived", 3),
                else_=4,
            ),
            desc(BuiltinsManifest.created_at),
        )

        manifests = db.execute(stmt).scalars().all()
        manifests_list = [_manifest_to_dict(m) for m in manifests]

        # Compute collection ETag
        etag = _compute_list_etag(manifests_list)

        # Cache result
        if redis_available():
            try:
                cache_set_json(
                    REDIS_MANIFEST_LIST,
                    {"manifests": manifests_list, "etag": etag},
                    ttl=TTL_LIST,
                )
            except Exception as exc:
                logger.warning("manifest_repo.list.cache_set_failed", extra={"error": str(exc)})

        logger.debug("manifest_repo.list.success", extra={"count": len(manifests_list)})

        return manifests_list, etag

    except Exception as exc:
        logger.error("manifest_repo.list.failed", extra={"error": str(exc)})
        raise


def list_history(limit: int = 50) -> tuple[list[dict[str, Any]], str]:
    """List recent activation history.

    Args:
        limit: Maximum number of activations to return (default 50)

    Returns:
        Tuple of (activations_list, collection_etag)
    """
    # Try cache first
    if redis_available():
        try:
            cached = cache_get_json(REDIS_MANIFEST_HISTORY)
            if cached:
                logger.debug("manifest_repo.history.cache_hit")
                return cached.get("activations", []), cached.get("etag", "")
        except Exception as exc:
            logger.warning("manifest_repo.history.cache_failed", extra={"error": str(exc)})

    db: Session = next(get_db())

    try:
        # Get recent activations with manifest details
        stmt = (
            select(BuiltinsActivation, BuiltinsManifest)
            .join(BuiltinsManifest, BuiltinsActivation.manifest_id == BuiltinsManifest.id)
            .order_by(desc(BuiltinsActivation.activated_at))
            .limit(limit)
        )

        results = db.execute(stmt).all()

        activations_list = []
        for activation, manifest in results:
            activations_list.append(
                {
                    "id": str(activation.id),
                    "manifest_id": str(activation.manifest_id),
                    "manifest_version": manifest.version,
                    "manifest_sha256": manifest.sha256,
                    "activated_at": activation.activated_at.isoformat() if activation.activated_at else None,
                    "activated_by_sub": activation.activated_by_sub,
                    "reason": activation.reason,
                    "previous_manifest_id": str(activation.previous_manifest_id)
                    if activation.previous_manifest_id
                    else None,
                    "trace_id": activation.trace_id,
                    "event_id": activation.event_id,
                }
            )

        # Compute collection ETag
        etag = _compute_history_etag(activations_list)

        # Cache result
        if redis_available():
            try:
                cache_set_json(
                    REDIS_MANIFEST_HISTORY,
                    {"activations": activations_list, "etag": etag},
                    ttl=TTL_HISTORY,
                )
            except Exception as exc:
                logger.warning("manifest_repo.history.cache_set_failed", extra={"error": str(exc)})

        logger.debug("manifest_repo.history.success", extra={"count": len(activations_list)})

        return activations_list, etag

    except Exception as exc:
        logger.error("manifest_repo.history.failed", extra={"error": str(exc)})
        raise


def get_active() -> dict[str, Any] | None:
    """Get currently active manifest.

    Returns:
        Active manifest dict or None if no active manifest
    """
    # Try cache first
    if redis_available():
        try:
            cached = cache_get_json(REDIS_MANIFEST_ACTIVE)
            if cached:
                logger.debug("manifest_repo.get_active.cache_hit")
                return cached
        except Exception as exc:
            logger.warning("manifest_repo.get_active.cache_failed", extra={"error": str(exc)})

    db: Session = next(get_db())

    try:
        stmt = select(BuiltinsManifest).where(BuiltinsManifest.state == "active")
        active = db.execute(stmt).scalar_one_or_none()

        if not active:
            return None

        active_dict = _manifest_to_dict(active)

        # Cache result
        if redis_available():
            try:
                cache_set_json(REDIS_MANIFEST_ACTIVE, active_dict, ttl=TTL_ACTIVE)
            except Exception as exc:
                logger.warning("manifest_repo.cache.active.failed", extra={"error": str(exc)})

        return active_dict

    except Exception as exc:
        logger.error("manifest_repo.get_active.failed", extra={"error": str(exc)})
        raise


def get_manifest_by_id(manifest_id: str) -> dict[str, Any] | None:
    """Get manifest by ID.

    Args:
        manifest_id: UUID of manifest to retrieve

    Returns:
        Manifest dict or None if not found
    """
    db: Session = next(get_db())

    try:
        stmt = select(BuiltinsManifest).where(BuiltinsManifest.id == UUID(manifest_id))
        manifest = db.execute(stmt).scalar_one_or_none()

        if not manifest:
            return None

        return _manifest_to_dict(manifest)

    except Exception as exc:
        logger.error("manifest_repo.get_by_id.failed", extra={"error": str(exc), "manifest_id": manifest_id})
        raise


def _manifest_to_dict(manifest: BuiltinsManifest) -> dict[str, Any]:
    """Convert manifest ORM object to dict."""
    return {
        "id": str(manifest.id),
        "source_url": manifest.source_url,
        "content": manifest.content_json,
        "sha256": manifest.sha256,
        "version": manifest.version,
        "state": manifest.state,
        "created_at": manifest.created_at.isoformat() if manifest.created_at else None,
        "activated_at": manifest.activated_at.isoformat() if manifest.activated_at else None,
        "created_by_sub": manifest.created_by_sub,
        "etag": manifest.etag,
        "updated_at": manifest.updated_at.isoformat() if manifest.updated_at else None,
    }


# Import sa for case expression
import sqlalchemy as sa
