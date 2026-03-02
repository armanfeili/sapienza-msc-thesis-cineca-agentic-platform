"""
Security headers middleware for production hardening.

Adds standard security headers to all responses:
- Strict-Transport-Security (HSTS)
- X-Frame-Options
- X-Content-Type-Options
- X-XSS-Protection
- Referrer-Policy
- Content-Security-Policy
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.config import settings

logger = logging.getLogger("cineca.middleware.security")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add security headers to all HTTP responses.

    Configurable via environment variables:
    - ENABLE_SECURITY_HEADERS: Enable/disable all security headers (default: true in production)
    - ENABLE_HSTS: Enable Strict-Transport-Security header (default: true in production)
    - HSTS_MAX_AGE: HSTS max-age in seconds (default: 31536000 = 1 year)
    - CSP_POLICY: Content-Security-Policy header value (default: restrictive)
    """

    def __init__(self, app, **kwargs):
        super().__init__(app)
        self.enabled = getattr(settings, "ENABLE_SECURITY_HEADERS", True)
        self.enable_hsts = getattr(settings, "ENABLE_HSTS", True)
        self.hsts_max_age = getattr(settings, "HSTS_MAX_AGE", 31536000)  # 1 year
        self.csp_policy = getattr(
            settings,
            "CSP_POLICY",
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:; connect-src 'self'",
        )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Add security headers to response."""
        response = await call_next(request)

        if not self.enabled:
            return response

        # HSTS (HTTP Strict Transport Security)
        # Only add if request came over HTTPS or via trusted proxy
        if self.enable_hsts:
            is_https = request.url.scheme == "https"
            is_forwarded_https = request.headers.get("x-forwarded-proto") == "https"

            if is_https or is_forwarded_https:
                response.headers["Strict-Transport-Security"] = f"max-age={self.hsts_max_age}; includeSubDomains"

        # X-Frame-Options: Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # X-Content-Type-Options: Prevent MIME sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # X-XSS-Protection: Enable browser XSS filter (legacy but harmless)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Referrer-Policy: Control referrer information
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Content-Security-Policy: Restrict resource loading
        # Note: This is a restrictive policy - adjust for your needs
        if self.csp_policy:
            response.headers["Content-Security-Policy"] = self.csp_policy

        # Permissions-Policy: Control browser features
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        # Remove Server header (done at nginx level too, but defense in depth)
        # Note: Use del instead of pop() for MutableHeaders
        if "Server" in response.headers:
            del response.headers["Server"]

        return response
