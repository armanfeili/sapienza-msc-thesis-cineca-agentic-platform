"""
Idempotency handling for POST requests.

Provides request deduplication using Idempotency-Key header with
two-tier caching (Redis + PostgreSQL).
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from typing import Any

from fastapi import HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from db.postgres_control.models.idempotency_key import IdempotencyKey
from db.postgres_control.repositories.agents import IdempotencyRepository
from db.redis_cache.agents import (
    cache_idempotent_response,
    get_idempotent_response,
)

logger = logging.getLogger(__name__)


_LOCAL_IDEMPOTENCY_STORE: dict[str, dict[str, Any]] = {}
_LOCAL_IDEMPOTENCY_LOCK = threading.Lock()
_IDEMPOTENCY_DB_AVAILABLE = True
_IDEMPOTENCY_DB_WARNING_EMITTED = False


def _set_db_unavailable(exc: Exception | None = None) -> None:
    global _IDEMPOTENCY_DB_AVAILABLE, _IDEMPOTENCY_DB_WARNING_EMITTED
    if _IDEMPOTENCY_DB_AVAILABLE:
        _IDEMPOTENCY_DB_AVAILABLE = False
        if not _IDEMPOTENCY_DB_WARNING_EMITTED:
            logger.warning(
                "PostgreSQL unavailable for idempotency; using in-memory fallback",
                extra={"error": str(exc) if exc else None},
            )
            _IDEMPOTENCY_DB_WARNING_EMITTED = True


def _cache_local_idempotent_result(
    idempotency_key: str,
    user_id: str,
    method: str,
    path: str,
    request_hash: str,
    response_hash: str,
    response_json: str,
    status_code: int,
) -> None:
    entry = {
        "owner_user_id": user_id,
        "method": method,
        "path": path,
        "request_hash": request_hash,
        "response_hash": response_hash,
        "response_json": response_json,
        "status_code": status_code,
    }
    with _LOCAL_IDEMPOTENCY_LOCK:
        _LOCAL_IDEMPOTENCY_STORE[idempotency_key] = entry


def _get_local_idempotent_response(idempotency_key: str) -> dict[str, Any] | None:
    with _LOCAL_IDEMPOTENCY_LOCK:
        entry = _LOCAL_IDEMPOTENCY_STORE.get(idempotency_key)
        if not entry:
            return None
        return dict(entry)


def _safe_db_rollback(db: Session | None) -> None:
    if not db:
        return
    try:
        db.rollback()
    except Exception:
        pass


def _idempotent_replay_from_local(
    response: Response,
    idempotency_key: str,
    user_id: str,
) -> dict[str, Any] | None:
    entry = _get_local_idempotent_response(idempotency_key)
    if not entry:
        return None

    if entry["owner_user_id"] != user_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Idempotency-Key owned by different user")

    try:
        response_body = json.loads(entry["response_json"])
    except Exception:
        response_body = {}

    response.headers["Idempotency-Replayed"] = "true"
    response.headers["Idempotency-Key"] = idempotency_key

    return {
        "body": response_body,
        "status_code": entry.get("status_code", 200),
    }


def compute_request_hash(body: dict[str, Any]) -> str:
    """
    Compute SHA256 hash of request body.

    Args:
        body: Request body dictionary

    Returns:
        Hex string of SHA256 hash
    """
    json_str = json.dumps(body, sort_keys=True, default=str)
    return hashlib.sha256(json_str.encode()).hexdigest()


def compute_response_hash(response: dict[str, Any]) -> str:
    """
    Compute SHA256 hash of response body.

    Args:
        response: Response body dictionary

    Returns:
        Hex string of SHA256 hash
    """
    json_str = json.dumps(response, sort_keys=True, default=str)
    return hashlib.sha256(json_str.encode()).hexdigest()


def handle_idempotency(
    request: Request,
    response: Response,
    user_id: str,
    db: Session,
    idempotency_key: str | None = None,
) -> dict[str, Any] | None:
    """
    Check for idempotent replay and return cached response if found.

    This function should be called at the start of POST endpoints that support
    idempotency. If a cached response is found, it should be returned immediately.

    Workflow:
    1. Check Redis cache (fast path)
    2. If not in Redis, check PostgreSQL
    3. If found in DB, cache in Redis and return
    4. If not found, return None (proceed with request)

    After processing the request, call cache_idempotent_result() to store the response.

    Args:
        request: FastAPI request object
        response: FastAPI response object (to set headers)
        user_id: Current user ID (for ownership)
        db: Database session
        idempotency_key: Optional idempotency key from header

    Returns:
        Dict with keys 'body' (response body) and 'status_code' (HTTP status) if replay,
        None if new request
    """
    # No idempotency key provided, proceed normally
    if not idempotency_key:
        return None

    # Validate key format (printable ASCII, max 255 chars)
    if len(idempotency_key) > 255 or not idempotency_key.isprintable():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Idempotency-Key format")

    # Check Redis cache first (fast path)
    cached = get_idempotent_response(idempotency_key)
    if cached:
        logger.info(f"Idempotency replay from Redis: {idempotency_key}")
        response.headers["Idempotency-Replayed"] = "true"
        response.headers["Idempotency-Key"] = idempotency_key
        return cached

    # Attempt to use PostgreSQL (durable storage)
    if _IDEMPOTENCY_DB_AVAILABLE:
        try:
            idem = db.query(IdempotencyKey).filter_by(key=idempotency_key).first()
        except Exception as exc:
            _set_db_unavailable(exc)
            idem = None

        if idem:
            logger.info(f"Idempotency replay from DB: {idempotency_key}")

            # Verify ownership
            if idem.owner_user_id != user_id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Idempotency-Key owned by different user")

            try:
                IdempotencyRepository.mark_replayed(db, idempotency_key)
                db.commit()
            except Exception as exc:
                _set_db_unavailable(exc)
                _safe_db_rollback(db)
            try:
                cached_response = json.loads(idem.response_body or "{}")
            except Exception:
                cached_response = {}

            status_code = int(idem.status_code or "200")

            cache_idempotent_response(
                idempotency_key,
                cached_response,
                status_code=status_code,
            )

            response.headers["Idempotency-Replayed"] = "true"
            response.headers["Idempotency-Key"] = idempotency_key

            return {
                "body": cached_response,
                "status_code": status_code,
            }

    # Check local fallback store if DB unavailable or miss
    local_replay = _idempotent_replay_from_local(response, idempotency_key, user_id)
    if local_replay:
        logger.info(f"Idempotency replay from local cache: {idempotency_key}")
        return local_replay

    # Not a replay, proceed with request
    return None


async def cache_idempotent_result(
    idempotency_key: str,
    user_id: str,
    method: str,
    path: str,
    request_body: dict[str, Any],
    response_body: dict[str, Any],
    status_code: int = 201,
    db: Session = None,
) -> None:
    """
    Cache the result of an idempotent request.

    Call this after successfully processing a POST request with an Idempotency-Key.

    Args:
        idempotency_key: Idempotency key from header
        user_id: Current user ID
        method: HTTP method (POST, etc.)
        path: Request path
        request_body: Request body dictionary
        response_body: Response body dictionary
        status_code: HTTP status code of the response (default 201 for creates)
        db: Database session
    """
    try:
        # Compute hashes
        req_hash = compute_request_hash(request_body)
        res_hash = compute_response_hash(response_body)

        response_json = json.dumps(response_body, default=str)

        if not db or not _IDEMPOTENCY_DB_AVAILABLE:
            _cache_local_idempotent_result(
                idempotency_key=idempotency_key,
                user_id=user_id,
                method=method,
                path=path,
                request_hash=req_hash,
                response_hash=res_hash,
                response_json=response_json,
                status_code=status_code,
            )
        else:
            try:
                IdempotencyRepository.get_or_create(
                    db=db,
                    key=idempotency_key,
                    owner_user_id=user_id,
                    method=method,
                    path=path,
                    request_hash=req_hash,
                    response_hash=res_hash,
                    response_body=response_json,
                    status_code=status_code,
                )
                db.commit()
            except Exception as exc:
                _set_db_unavailable(exc)
                _safe_db_rollback(db)
                _cache_local_idempotent_result(
                    idempotency_key=idempotency_key,
                    user_id=user_id,
                    method=method,
                    path=path,
                    request_hash=req_hash,
                    response_hash=res_hash,
                    response_json=response_json,
                    status_code=status_code,
                )

        # Store in PostgreSQL with status_code
        cache_idempotent_response(
            idempotency_key,
            response_body,
            status_code=status_code,
        )

        logger.info(f"Cached idempotent result: {idempotency_key} (status={status_code})")

    except Exception as exc:
        logger.error(f"Failed to cache idempotent result: {exc}")
        _safe_db_rollback(db)


class IdempotencyHandler:
    """
    Reusable idempotency handler for FastAPI endpoints.

    Usage:
        @router.post("/resource")
        async def create_resource(
            request: Request,
            response: Response,
            data: CreateRequest,
            user: UserInfo = Depends(get_current_user),
            db: Session = Depends(get_db),
            idem_key: Optional[str] = Header(None, alias="Idempotency-Key"),
        ):
            # Check for replay
            handler = IdempotencyHandler(request, response, user.sub, db, idem_key)
            cached = await handler.check()
            if cached:
                return cached

            # Process request
            result = create_resource_logic(data)

            # Cache result
            await handler.cache(data.dict(), result.dict())

            return result
    """

    def __init__(
        self,
        request: Request,
        response: Response,
        user_id: str,
        db: Session,
        idempotency_key: str | None,
    ):
        self.request = request
        self.response = response
        self.user_id = user_id
        self.db = db
        self.idempotency_key = idempotency_key

    def check(self) -> dict[str, Any] | None:
        """
        Check for idempotent replay.

        Returns:
            Cached response if replay, None if new request
        """
        return handle_idempotency(
            request=self.request,
            response=self.response,
            user_id=self.user_id,
            db=self.db,
            idempotency_key=self.idempotency_key,
        )

    async def cache(
        self,
        request_body: dict[str, Any],
        response_body: dict[str, Any],
        status_code: int = 201,
    ) -> None:
        """
        Cache the result of the request.

        Args:
            request_body: Request body dictionary
            response_body: Response body dictionary
            status_code: HTTP status code of the response (default 201 for creates)
        """
        if not self.idempotency_key:
            return

        await cache_idempotent_result(
            idempotency_key=self.idempotency_key,
            user_id=self.user_id,
            method=self.request.method,
            path=str(self.request.url.path),
            request_body=request_body,
            response_body=response_body,
            status_code=status_code,
            db=self.db,
        )


__all__ = [
    "IdempotencyHandler",
    "cache_idempotent_result",
    "compute_request_hash",
    "compute_response_hash",
    "handle_idempotency",
]
