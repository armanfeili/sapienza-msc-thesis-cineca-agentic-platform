"""
Vary header middleware for cache-aware HTTP responses.

The Vary header indicates which request headers the response depends on.
This middleware adds Vary headers to responses to ensure proper cache behavior.

RFC 7231: The Vary header field-value indicates the set of request-header
fields that fully determines whether a response message is applicable to a
request without further validation.

When cached responses are retrieved, the Vary header tells caches whether
a new request with different header values should bypass the cache.

Model
-----
- Responses scoped to Authorization header are marked: Vary: Authorization
- Responses scoped to Authorization + X-Default-Scope are marked: Vary: Authorization, X-Default-Scope
- Responses scoped to Authorization + X-Tenant-Id are marked: Vary: Authorization, X-Tenant-Id
- Public responses (no auth required) are marked: Vary: Accept-Encoding

API
---
- add_vary_headers: FastAPI middleware factory
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import Response

logger = logging.getLogger(__name__)


# Endpoints that should have Vary: Authorization headers
# These endpoints return different content based on Authorization header
VARY_AUTHORIZATION_PATHS = [
    "/v1/agents/sessions",
    "/v1/agents/sessions/",
    "/v1/agent-runs",
    "/v1/agent-runs/",
    "/v1/jobs",
    "/v1/jobs/",
    "/v1/admin/jobs",
    "/v1/admin/jobs/",
    "/v1/models/",
    "/v1/models",
]

# Endpoints that should have Vary: Authorization, X-Default-Scope headers
# These endpoints return different content based on both headers
VARY_AUTHORIZATION_SCOPE_PATHS = [
    "/v1/tools",
    "/v1/tools/",
]

# Endpoints that should have Vary: Authorization, X-Tenant-Id headers
# These endpoints return different content based on both headers
VARY_AUTHORIZATION_TENANT_PATHS = [
    "/v1/admin/tenants",
    "/v1/admin/tenants/",
]


def _should_vary_on_auth(path: str) -> bool:
    """Check if path should have Authorization in Vary header."""
    return any(path.startswith(p) for p in VARY_AUTHORIZATION_PATHS)


def _should_vary_on_auth_scope(path: str) -> bool:
    """Check if path should have Authorization + X-Default-Scope in Vary header."""
    return any(path.startswith(p) for p in VARY_AUTHORIZATION_SCOPE_PATHS)


def _should_vary_on_auth_tenant(path: str) -> bool:
    """Check if path should have Authorization + X-Tenant-Id in Vary header."""
    return any(path.startswith(p) for p in VARY_AUTHORIZATION_TENANT_PATHS)


def add_vary_headers(app: FastAPI) -> None:
    """
    Add Vary header middleware to FastAPI app.

    Middleware adds appropriate Vary headers based on the request path
    and response type to ensure proper cache behavior with ETags.

    Args:
        app: FastAPI application instance
    """

    @app.middleware("http")
    async def vary_middleware(request: Request, call_next) -> Response:
        """Add Vary headers to responses based on request path."""
        response = await call_next(request)

        path = request.url.path

        # Skip adding Vary headers to error responses or non-GET/HEAD requests
        # (though GET/HEAD are typically cacheable and should have Vary)
        if response.status_code >= 400:
            return response

        # Add Vary headers based on endpoint type
        vary_header = None

        if _should_vary_on_auth_tenant(path):
            # Multi-tenant endpoints: vary on both Authorization and X-Tenant-Id
            vary_header = "Authorization, X-Tenant-Id"
        elif _should_vary_on_auth_scope(path):
            # Scope-aware endpoints: vary on both Authorization and X-Default-Scope
            vary_header = "Authorization, X-Default-Scope"
        elif _should_vary_on_auth(path):
            # Authorization-dependent endpoints: vary on Authorization
            vary_header = "Authorization"
        else:
            # Public endpoints: vary on Accept-Encoding (for compression)
            vary_header = "Accept-Encoding"

        if vary_header:
            # Merge with existing Vary header if present
            existing_vary = response.headers.get("vary")
            if existing_vary:
                # Merge and deduplicate
                parts = set()
                for part in existing_vary.split(","):
                    parts.add(part.strip())
                for part in vary_header.split(","):
                    parts.add(part.strip())
                response.headers["vary"] = ", ".join(sorted(parts))
            else:
                response.headers["vary"] = vary_header

        return response


__all__ = [
    "add_vary_headers",
]
