"""
HTTP observability middleware for the Cineca Agentic Platform.

Responsibilities
- Generate / propagate X-Request-ID and expose it on responses
- Time every request and expose `X-Process-Time` response header
- Record Prometheus metrics via `observability.metrics.record_request`
- (If OpenTelemetry is active) attach current trace id as `X-Trace-Id`
- Bind useful context into structlog for consistent, correlated logs
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable

import structlog
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from structlog.contextvars import bind_contextvars, unbind_contextvars

try:  # Optional OpenTelemetry
    from opentelemetry import trace as otel_trace  # type: ignore
except Exception:  # pragma: no cover - optional
    otel_trace = None  # type: ignore

from .metrics import record_request

log = structlog.get_logger(__name__)


def _get_route_template(request: Request) -> str:
    """
    Best-effort way to obtain the parameterized route path (low-cardinality).
    Falls back to the raw URL path if no route is available.
    """
    route = request.scope.get("route")
    if route and getattr(route, "path", None):
        return route.path  # e.g. "/items/{item_id}"
    # Fallback to raw path, but try to reduce cardinality a little
    return request.url.path


def _current_trace_id() -> str | None:
    if not otel_trace:
        return None
    try:
        span = otel_trace.get_current_span()
        ctx = span.get_span_context()
        if ctx and getattr(ctx, "trace_id", 0):
            return f"{ctx.trace_id:032x}"
    except Exception:  # pragma: no cover - defensive
        return None
    return None


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """
    Starlette middleware that emits Prometheus metrics, binds logging context,
    and sets correlation headers for every request.
    """

    def __init__(self, app: FastAPI) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        started = time.perf_counter()

        # Correlation id (prefer incoming)
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = request_id  # downstream access

        # Low-cardinality route template (might be filled by router)
        route_template = _get_route_template(request)

        # Bind logging context
        bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=route_template,
            client_ip=request.client.host if request.client else None,
        )

        trace_id = _current_trace_id()
        if trace_id:
            bind_contextvars(trace_id=trace_id)

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            # Ensure 5xx is recorded even if an exception bubbles
            status_code = 500
            duration = max(0.0, time.perf_counter() - started)
            # Debug: log what we would record for failed requests
            try:
                log.debug(
                    "observability.middleware.recording",
                    method=request.method,
                    path=route_template,
                    status=status_code,
                    duration_s=duration,
                    note="exception-path",
                )
                record_request(
                    method=request.method,
                    path_template=route_template,
                    status_code=status_code,
                    duration_seconds=duration,
                    app=request.app,
                )
                log.debug(
                    "observability.middleware.recorded", method=request.method, path=route_template, status=status_code
                )
            except Exception:
                log.exception("observability.middleware.record_failed")

            log.exception(
                "http.request.error",
                status=status_code,
                duration_s=duration,
            )
            # Re-raise so default exception handlers run
            raise

        # Compute duration and record metrics
        duration = max(0.0, time.perf_counter() - started)
        # Debug: log before recording so we can see middleware is running
        try:
            log.debug(
                "observability.middleware.recording",
                method=request.method,
                path=route_template,
                status=response.status_code,
                duration_s=duration,
                note="normal-path",
            )
            record_request(
                method=request.method,
                path_template=route_template,
                status_code=status_code,
                duration_seconds=duration,
                app=request.app,
            )
            log.debug(
                "observability.middleware.recorded",
                method=request.method,
                path=route_template,
                status=response.status_code,
            )
        except Exception:
            log.exception("observability.middleware.record_failed")

        # Correlation headers & timing
        try:
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = f"{duration:.6f}s"
            if trace_id:
                response.headers["X-Trace-Id"] = trace_id
        except Exception:  # pragma: no cover - very defensive
            pass

        # Minimal structured access log (one per request)
        log.info(
            "http.request",
            status=status_code,
            duration_s=duration,
            user_agent=request.headers.get("user-agent"),
        )

        # Unbind per-request context
        unbind_contextvars("request_id", "method", "path", "client_ip", "trace_id")

        return response


def install_observability_middleware(app: FastAPI) -> None:
    """
    Convenience helper to add this middleware to a FastAPI app.

    Example:
        app = FastAPI()
        install_observability_middleware(app)
    """
    app.add_middleware(ObservabilityMiddleware)


__all__ = ["ObservabilityMiddleware", "install_observability_middleware"]
