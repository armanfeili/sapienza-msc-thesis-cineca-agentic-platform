"""Rate limiting middleware for FastAPI endpoints using Redis sliding window."""

from __future__ import annotations

from fastapi import HTTPException, Request, Response

from db.redis_cache.rate_limit import (
    check_rate_limit,
    get_rate_limit_config,
    make_rate_limit_key,
)
from src.schemas.agents import ProblemDetail


class RateLimitHandler:
    """
    Handler for rate limiting with RFC 6585 compliant responses.

    Supports both per-user and per-tenant quotas.

    Usage in endpoints:
        handler = RateLimitHandler(user_id=user.sub, tenant_id=user.tenant_id)
        await handler.check("sessions:create")
        # ... proceed with request ...
    """

    def __init__(self, user_id: str, tenant_id: str | None = None, resource_id: str | None = None):
        """
        Initialize rate limit handler.

        Args:
            user_id: User ID to rate limit
            tenant_id: Optional tenant ID for tenant-level quotas
            resource_id: Optional resource ID (e.g., session_id for per-session limits)
        """
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.resource_id = resource_id

    async def check(self, action: str) -> None:
        """
        Check rate limit and raise HTTPException if exceeded.

        Checks both per-user rate limits and per-tenant quotas (if tenant_id provided).

        Args:
            action: Action being rate limited (e.g., "sessions:create")

        Raises:
            HTTPException: 429 Too Many Requests if limit exceeded
        """
        # Check per-user rate limit first
        limit, window = get_rate_limit_config(action)
        key = make_rate_limit_key(action, self.user_id, self.resource_id)

        allowed, _remaining, retry_after = await check_rate_limit(key, limit, window)

        if not allowed:
            # Standardized error envelope with code E_RATE_LIMIT
            raise HTTPException(
                status_code=429,
                detail={
                    "ok": False,
                    "code": "E_RATE_LIMIT",
                    "message": f"Rate limit exceeded: {limit} requests per {window} seconds",
                    "retry_after": retry_after,
                    "limit": limit,
                    "window": window,
                    "scope": "user",
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Window": str(window),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Scope": "user",
                },
            )

        # Check tenant quota if tenant_id provided
        if self.tenant_id:
            from db.redis_cache.rate_limit import check_tenant_quota

            tenant_allowed, _tenant_remaining, tenant_retry = await check_tenant_quota(action, self.tenant_id)

            if not tenant_allowed:
                # Tenant quota exceeded
                tenant_limit, tenant_window = get_rate_limit_config(f"tenant:{action}")

                raise HTTPException(
                    status_code=429,
                    detail={
                        "ok": False,
                        "code": "E_TENANT_QUOTA",
                        "message": f"Tenant quota exceeded: {tenant_limit} requests per {tenant_window} seconds",
                        "retry_after": tenant_retry,
                        "limit": tenant_limit,
                        "window": tenant_window,
                        "scope": "tenant",
                    },
                    headers={
                        "Retry-After": str(tenant_retry),
                        "X-RateLimit-Limit": str(tenant_limit),
                        "X-RateLimit-Window": str(tenant_window),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Scope": "tenant",
                    },
                )

    async def check_and_add_headers(self, action: str, response: Response) -> None:
        """
        Check rate limit and add rate limit headers to response.

        Args:
            action: Action being rate limited
            response: FastAPI Response object to add headers to

        Raises:
            HTTPException: 429 if limit exceeded
        """
        limit, window = get_rate_limit_config(action)
        key = make_rate_limit_key(action, self.user_id, self.resource_id)

        allowed, remaining, retry_after = await check_rate_limit(key, limit, window)

        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Window"] = str(window)

        if not allowed:
            response.headers["Retry-After"] = str(retry_after)

            problem = ProblemDetail(
                type="https://httpstatuses.com/429",
                title="Too Many Requests",
                status=429,
                detail=f"Rate limit exceeded: {limit} requests per {window} seconds. Try again in {retry_after} seconds.",
                instance=None,
                extensions={
                    "limit": limit,
                    "window": window,
                    "retry_after": retry_after,
                },
            )

            raise HTTPException(
                status_code=429,
                detail=problem.model_dump(),
                headers=dict(response.headers),
            )


def rate_limit_dependency(action: str, resource_id_param: str | None = None):
    """
    Create a FastAPI dependency for rate limiting.

    Args:
        action: Action to rate limit (e.g., "sessions:create")
        resource_id_param: Optional parameter name for resource ID (e.g., "session_id")

    Returns:
        Dependency function for FastAPI

    Example:
        @router.post("/sessions", dependencies=[Depends(rate_limit_dependency("sessions:create"))])
        async def create_session(...):
            ...
    """

    async def dependency(request: Request, user=None):
        if not user:
            # Try to get user from request state (set by auth middleware)
            user = getattr(request.state, "user", None)

        if not user:
            # No user = no rate limiting (public endpoints)
            return

        user_id = getattr(user, "sub", None) or getattr(user, "user_id", None)
        if not user_id:
            return

        # Get resource ID from path params if specified
        resource_id = None
        if resource_id_param:
            resource_id = request.path_params.get(resource_id_param)

        handler = RateLimitHandler(user_id=user_id, resource_id=resource_id)
        await handler.check(action)

    return dependency


async def add_rate_limit_headers(
    response: Response,
    user_id: str,
    action: str,
    resource_id: str | None = None,
) -> None:
    """
    Add rate limit headers to response without checking limit.

    Useful for adding informational headers after request succeeds.

    Args:
        response: FastAPI Response object
        user_id: User ID
        action: Action that was performed
        resource_id: Optional resource ID
    """
    from db.redis_cache.rate_limit import get_rate_limit_status

    limit, window = get_rate_limit_config(action)
    key = make_rate_limit_key(action, user_id, resource_id)

    _current, remaining, reset_in = await get_rate_limit_status(key, limit, window)

    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Window"] = str(window)
    if reset_in > 0:
        response.headers["X-RateLimit-Reset"] = str(reset_in)
