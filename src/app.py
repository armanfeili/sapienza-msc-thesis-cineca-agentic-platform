"""
FastAPI application factory for the Cineca Agentic Platform.

Minimal, robust app factory used for local development and tests.
Provides Swagger UI per version with configurable auth controls.
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import os
import re
import time
import uuid
from collections.abc import Iterable
from contextlib import suppress
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel

from src.middleware.vary_headers import add_vary_headers

# Preferred ordering for OpenAPI tags shown in the UI. Keep common groups first.
PREFERRED_TAG_ORDER = [
    "meta",
    "health",
    "auth",
    "admin-tenants",
    "models-providers",
    "models-manifests-builtins",
    "models-instances",
    "tools",
    "jobs",
    "agents",
    "admin-processes",
    "admin-ops",
    "admin-db",
    "internal-ops",
    "internal-db",
]

# Import runtime settings from the project's config module. This replaces a temporary shim used during iterative edits.
from src.config import settings
from src.utils.provider_resolver import (
    DEFAULT_HTTPX_TIMEOUT,
    is_ollama_provider,
    resolve_provider_base_url,
    timeout_for_provider,
)

# Global logger (configured at app startup by structlog setup)
logger = logging.getLogger("cineca.app")

# Request id contextvar used by middleware and logging filter
_request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
# Traceparent and tenant contextvars
_trace_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("traceparent", default=None)
_tenant_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("tenant_id", default="global")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            rid = _request_id_ctx.get()
        except Exception:
            rid = None
        record.request_id = rid
        return True


# Attach the filter so logs include request_id as attribute (formatter can use it)
logger.addFilter(RequestIdFilter())


def _docs_urls(enabled: bool) -> tuple[str | None, str | None, str | None]:
    # Disable FastAPI's built-in /docs so we can provide a custom wrapper when enabled
    if enabled:
        return None, "/redoc", "/openapi.json"
    return None, None, None


def _mount_metrics(app: FastAPI) -> None:
    # Optional: try to mount prometheus if available; ignore failures.
    if not settings.PROMETHEUS_METRICS_ENABLED:
        return
    try:
        from prometheus_client import make_asgi_app  # type: ignore

        app.mount("/metrics", make_asgi_app())
        logger.info("Mounted /metrics")
    except Exception:
        logger.debug("Prometheus not available; skipping /metrics")


def create_app() -> FastAPI:
    # Initialize structured logging early using the project's logging_setup module.
    try:
        # Ensure structured JSON logs by default for better observability.
        # Operators can override via LOG_FORMAT or APP_ENV.
        os.environ.setdefault("LOG_FORMAT", "json")
        from src.logging_setup import setup_logging

        setup_logging(level=settings.LOG_LEVEL)
    except Exception:
        # fallback to basic logging configuration
        logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

    # Ensure RequestIdFilter is attached to root logger so non-structlog records have request_id attribute
    try:
        root = logging.getLogger()
        root.addFilter(RequestIdFilter())
    except Exception:
        pass

    # Install sensitive data masking for logs (P2.5: Secrets & Config Hardening)
    try:
        from src.security.secrets import install_log_masking, validate_secrets_on_startup

        # Install log masking filter
        install_log_masking()

        # Validate secrets (raises in production if critical secrets missing/insecure)
        secret_summary = validate_secrets_on_startup(settings)
        if secret_summary.get("warning_count", 0) > 0:
            logger.warning(
                f"[SECURITY] Secret validation warnings: {secret_summary['warning_count']} " f"(see logs for details)"
            )
    except Exception as e:
        logger.error(f"[SECURITY] Failed to initialize secrets validation: {e}")
        # Don't fail startup, but log prominently
        pass

    # Disable FastAPI's built-in docs; we provide only versioned UIs at /v1/docs and /v2/docs
    app = FastAPI(
        title="Cineca Agentic Platform",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url="/openapi.json",
    )

    # ──────────────────────────────────────────────────────────────────
    # Startup Event: Provider Alignment & DMR Warmup
    # ──────────────────────────────────────────────────────────────────
    @app.on_event("startup")
    async def startup_init_default_model():
        """
        Initialize default model at startup:
        1. Resolve default from DMR (not env var)
        2. Align provider configuration if needed
        3. Warmup model for fast first request
        """
        try:
            from src.services.default_model_resolver import DefaultModelResolver
            from src.services.model_warmup import get_warmup_service
            
            dmr = DefaultModelResolver()
            
            # Step 1: Resolve default model from DMR
            logger.info("startup.default_model.resolving", extra={"scope": "global"})
            default_result = await dmr.get_default_model(tenant_id=None, scope="global")
            
            if not default_result:
                logger.warning(
                    "startup.no_default_model",
                    extra={"action": "skipped", "reason": "no_default_configured"}
                )
                return
            
            model_id = default_result.get("model_id")
            source = default_result.get("source", "unknown")
            
            logger.info(
                "startup.default_model.resolved",
                extra={"model_id": model_id, "source": source}
            )
            
            # Step 2: Check provider alignment (optional - depends on provider repo availability)
            try:
                from db.postgres_control.repositories import provider_repo
                
                # Get provider for this model (if available)
                provider_id = default_result.get("provider_id")
                if provider_id:
                    provider = provider_repo.get_provider(provider_id)
                    if provider:
                        provider_model = provider.get("model")
                        if provider_model and provider_model != model_id:
                            logger.info(
                                "startup.provider_model.mismatch",
                                extra={
                                    "provider_id": provider_id,
                                    "provider_model": provider_model,
                                    "default_model": model_id,
                                    "action": "alignment_recommended"
                                }
                            )
            except Exception as prov_exc:
                # Non-fatal: Provider alignment is best-effort
                logger.debug(f"startup.provider_alignment.skipped: {prov_exc}")
            
            # Step 3: Warmup model
            logger.info("startup.model_warmup.starting", extra={"model_id": model_id})
            warmup_service = get_warmup_service()
            warmup_result = await warmup_service.warmup_model(
                model_id=model_id,
                provider_id=default_result.get("provider_id", "unknown")
            )
            
            if warmup_result["success"]:
                logger.info(
                    "startup.model_warmup.succeeded",
                    extra={
                        "model_id": model_id,
                        "duration_ms": warmup_result["duration_ms"],
                        "attempts": warmup_result["attempts"]
                    }
                )
            else:
                logger.warning(
                    "startup.model_warmup.failed",
                    extra={
                        "model_id": model_id,
                        "error": warmup_result["error"],
                        "attempts": warmup_result["attempts"]
                    }
                )
            
            # Step 4: Warmup DMR cache
            logger.info("startup.dmr_cache.warming", extra={"scope": "global"})
            await dmr.warmup_cache(tenant_id=None, scope="global")
            logger.info("startup.dmr_cache.warmed", extra={"scope": "global"})
            
            # Step 5: Start provider health background scheduler
            try:
                from src.background.provider_health_scheduler import get_scheduler
                scheduler = get_scheduler()
                await scheduler.start()
                logger.info("startup.provider_health_scheduler.started")
            except Exception as sched_exc:
                # Non-fatal: Scheduler is optional
                logger.warning(
                    f"startup.provider_health_scheduler.failed: {sched_exc}",
                    extra={"action": "continued"},
                    exc_info=True
                )
            
            # Step 6: Warmup orchestrator models (from compute config)
            try:
                from src.config_modules.compute import get_compute_config
                compute_cfg = get_compute_config()
                
                if compute_cfg.warmup_models:
                    logger.info(
                        "startup.orchestrator_models.warming",
                        extra={"models": compute_cfg.warmup_models}
                    )
                    
                    for model_name in compute_cfg.warmup_models:
                        if not model_name:
                            continue
                        
                        logger.info(
                            "startup.orchestrator_model.warmup_started",
                            extra={"model": model_name}
                        )
                        
                        warmup_result = await warmup_service.warmup_model(
                            model_id=model_name,
                            provider_id="ollama"  # Default to Ollama for orchestrator models
                        )
                        
                        if warmup_result["success"]:
                            logger.info(
                                "startup.orchestrator_model.warmup_succeeded",
                                extra={
                                    "model": model_name,
                                    "duration_ms": warmup_result["duration_ms"],
                                }
                            )
                        else:
                            logger.warning(
                                "startup.orchestrator_model.warmup_failed",
                                extra={
                                    "model": model_name,
                                "error": warmup_result.get("error"),
                            }
                        )
                else:
                    logger.info(
                        "startup.orchestrator_models.no_env_overrides",
                        extra={"note": "No orchestrator model overrides provided via environment; using DB defaults"}
                    )
                    
            except Exception as warmup_exc:
                # Non-fatal: Orchestrator warmup is optional
                logger.warning(
                    f"startup.orchestrator_warmup.failed: {warmup_exc}",
                    extra={"action": "continued"},
                    exc_info=True
                )
            
        except Exception as exc:
            # Non-fatal: Startup continues even if warmup fails
            logger.warning(
                f"startup.init_default_model.failed: {exc}",
                extra={"action": "continued"},
                exc_info=True
            )
    
    @app.on_event("shutdown")
    async def shutdown_cleanup():
        """Gracefully shutdown background tasks."""
        logger.info("shutdown.cleanup.start")
        
        try:
            # Stop provider health scheduler
            from src.background.provider_health_scheduler import get_scheduler
            scheduler = get_scheduler()
            await scheduler.stop()
            logger.info("shutdown.provider_health_scheduler.stopped")
        except Exception as exc:
            logger.warning(
                f"shutdown.cleanup.failed: {exc}",
                exc_info=True
            )

    # CORS
    def _split_csv(v: str | Iterable[str]) -> list[str]:
        items = [s.strip() for s in v.split(",") if s.strip()] if isinstance(v, str) else list(v)
        return items or ["*"]

    # Add security headers middleware (must be first for headers to apply to all responses)
    from src.middleware.security_headers import SecurityHeadersMiddleware

    app.add_middleware(SecurityHeadersMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_split_csv(settings.CORS_ALLOWED_ORIGINS),
        allow_methods=_split_csv(settings.CORS_ALLOWED_METHODS),
        # Allow all request headers to avoid preflight failures (e.g., idempotency-key)
        allow_headers=["*"],
        expose_headers=[
            "X-Request-Id",
            "Location",
            "Idempotency-Key",
            "Idempotency-Replayed",
            "ETag",
            "Vary",
        ],
        allow_credentials=True,
    )

    # Request ID middleware: accept X-Request-ID or generate one, store in contextvar
    @app.middleware("http")
    async def request_id_middleware(request, call_next):
        try:
            # prefer configured header if available from pydantic settings
            try:
                from src.config import settings as psettings

                header_name = getattr(psettings, "REQUEST_ID_HEADER", "X-Request-Id")
            except Exception:
                header_name = "X-Request-Id"
            rid = request.headers.get(header_name) or str(uuid.uuid4())
            # optional correlation id header passed from callers
            corr = request.headers.get("X-Correlation-Id") or None
            # Propagate W3C traceparent header into logging context if present
            try:
                traceparent = request.headers.get("traceparent")
                if traceparent:
                    structlog.contextvars.bind_contextvars(traceparent=traceparent)
                    # store in a contextvar for problem details
                    with suppress(Exception):
                        _trace_ctx.set(traceparent)
            except Exception:
                pass
            # Bind into structlog contextvars so structured logs include request_id and correlation id
            try:
                structlog.contextvars.bind_contextvars(request_id=rid)
                if corr:
                    structlog.contextvars.bind_contextvars(correlation_id=corr)
            except Exception:
                # if structlog not configured yet or unavailable, continue
                pass
            _request_id_ctx.set(rid)
            # store correlation id on request.state for downstream handlers
            with suppress(Exception):
                request.state.correlation_id = corr
            # ensure header is present on response (but don't overwrite if a handler set it)
            response = await call_next(request)
            try:
                # Case-insensitive check for existing X-Request-Id
                has_req_id = any(k.lower() == "x-request-id" for k in response.headers)
            except Exception:
                has_req_id = False
            if not has_req_id:
                response.headers[header_name] = rid
            if corr:
                with suppress(Exception):
                    response.headers["X-Correlation-Id"] = corr
            return response
        except Exception:
            # In case of middleware failure, continue without request-id
            return await call_next(request)

    # RFC7807 Problem Details model with extensions
    class ProblemDetails(BaseModel):
        type: str | None = None
        title: str | None = None
        status: int | None = None
        detail: str | None = None
        instance: str | None = None
        # Use extensions.correlation_id instead of top-level traceId for consistency
        extensions: dict | None = None

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request, exc: HTTPException):
        try:
            rid = _request_id_ctx.get()
        except Exception:
            rid = None
        corr = None
        try:
            corr = request.headers.get("X-Correlation-Id")
        except Exception:
            corr = None
        if not corr:
            corr = rid

        # Check if the detail is already a ProblemDetail dict
        detail_dict = None
        if isinstance(exc.detail, dict):
            detail_dict = exc.detail.copy()

        # Allow routes to attach additional extension metadata via `extensions_extra`
        extensions_extra = {}
        try:
            maybe_extra = getattr(exc, "extensions_extra", None)
            if isinstance(maybe_extra, dict):
                extensions_extra.update(maybe_extra)
        except Exception:
            pass

        # Build base extensions with correlation_id and timestamp
        from datetime import datetime

        base_ext = {"correlation_id": corr, "timestamp": datetime.utcnow().isoformat() + "Z"}

        # If detail was already a ProblemDetail, merge extensions and preserve type/title
        if detail_dict and "type" in detail_dict:
            # Merge extensions, preserving existing ones
            existing_ext = detail_dict.get("extensions") or {}
            merged_ext = {**extensions_extra, **existing_ext, **base_ext}
            detail_dict["extensions"] = merged_ext
            headers = {}
            # Copy headers from exception (e.g., Retry-After for 429)
            if exc.headers:
                headers.update(exc.headers)
            if corr:
                headers["X-Correlation-Id"] = corr
            if rid and "X-Request-Id" not in headers:
                headers["X-Request-Id"] = rid
            return JSONResponse(
                status_code=exc.status_code, content=detail_dict, media_type="application/problem+json", headers=headers
            )

        # Otherwise, create a new ProblemDetail
        try:
            merged_ext = {**extensions_extra, **base_ext}
        except Exception:
            merged_ext = base_ext

        # Map status code to proper title (RFC 7807 compliance)
        status_titles = {
            400: "Bad Request",
            401: "Unauthorized",
            403: "Forbidden",
            404: "Not Found",
            405: "Method Not Allowed",
            409: "Conflict",
            413: "Payload Too Large",
            415: "Unsupported Media Type",
            422: "Validation Error",
            429: "Too Many Requests",
            500: "Internal Server Error",
            502: "Bad Gateway",
            503: "Service Unavailable",
            504: "Gateway Timeout",
        }
        title = status_titles.get(exc.status_code, "HTTP Error")

        prob = ProblemDetails(
            type="about:blank",
            title=title,
            status=exc.status_code,
            detail=str(getattr(exc, "detail", "")),
            instance=getattr(request, "url", None) and getattr(request.url, "path", None),
            extensions=merged_ext,
        )
        headers = {}
        # Copy headers from exception (e.g., Retry-After for 429)
        if exc.headers:
            headers.update(exc.headers)
        if corr:
            headers["X-Correlation-Id"] = corr
        # Always propagate X-Request-Id when available
        if rid and "X-Request-Id" not in headers:
            headers["X-Request-Id"] = rid
        return JSONResponse(
            status_code=exc.status_code,
            content=prob.model_dump(),
            media_type="application/problem+json",
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request, exc: RequestValidationError):
        try:
            rid = _request_id_ctx.get()
        except Exception:
            rid = None
        corr = None
        try:
            corr = request.headers.get("X-Correlation-Id")
        except Exception:
            corr = None
        if not corr:
            corr = rid
        prob = ProblemDetails(
            type="https://example.com/probs/validation",
            title="Validation Error",  # Match status code title
            status=422,
            detail="Request validation failed",
            instance=getattr(request, "url", None) and getattr(request.url, "path", None),
            extensions={"correlation_id": corr},
        )
        body = prob.model_dump()
        body["errors"] = jsonable_encoder(exc.errors())
        headers = {"X-Correlation-Id": corr} if corr else {}
        if rid and "X-Request-Id" not in headers:
            headers["X-Request-Id"] = rid
        return JSONResponse(status_code=422, content=body, media_type="application/problem+json", headers=headers)

    @app.exception_handler(Exception)
    async def generic_exception_handler(request, exc: Exception):
        try:
            rid = _request_id_ctx.get()
        except Exception:
            rid = None
        corr = None
        try:
            corr = request.headers.get("X-Correlation-Id")
        except Exception:
            corr = None
        if not corr:
            corr = rid
        prob = ProblemDetails(
            type="about:blank",
            title="Internal Server Error",  # Match status code title (proper case)
            status=500,
            detail=str(exc) or "Internal server error",
            instance=getattr(request, "url", None) and getattr(request.url, "path", None),
            extensions={"correlation_id": corr},
        )
        # Enhanced diagnostic logging (temporary) to capture full traceback for IndexError on /v1/admin/models/instances
        try:  # pragma: no cover - diagnostic only
            import traceback as _tb

            trace_txt = _tb.format_exc()
            logger.error(
                "diagnostic.unhandled",
                extra={
                    "path": getattr(request, "url", None) and getattr(request.url, "path", None),
                    "error": str(exc),
                    "trace": trace_txt,
                },
            )
        except Exception:
            pass
        headers = {"X-Correlation-Id": corr} if corr else {}
        if rid:
            headers.setdefault("X-Request-Id", rid)
        return JSONResponse(
            status_code=500, content=prob.model_dump(), media_type="application/problem+json", headers=headers
        )

    # Content-Type and request size middleware
    @app.middleware("http")
    async def content_type_and_size_middleware(request, call_next):
        # Enforce JSON for POST/PUT/PATCH
        if request.method in ("POST", "PUT", "PATCH"):
            # If request has no body (no Content-Length or length == 0), allow it
            cl = request.headers.get("content-length")
            try:
                if cl is None or int(cl) == 0:
                    return await call_next(request)
            except Exception:
                # If content-length is not parseable, fall back to enforcing content-type
                pass

            ct = request.headers.get("content-type", "")
            # Allow JSON, form-encoded, and multipart content types to support
            # OAuth2 token endpoint (form) and multipart uploads.
            allowed = ("application/json", "application/x-www-form-urlencoded", "multipart/form-data")
            if not any(ct.startswith(a) for a in allowed):
                try:
                    rid = _request_id_ctx.get()
                except Exception:
                    rid = None
                prob = ProblemDetails(
                    type="about:blank",
                    title="Unsupported Media Type",
                    status=415,
                    detail="Content-Type must be application/json or form-encoded",
                    extensions={"correlation_id": rid},
                )
                return JSONResponse(status_code=415, content=prob.model_dump(), media_type="application/problem+json")

        # Global request size limit (default 1MB)
        try:
            max_size = int(os.getenv("MAX_REQUEST_BODY_BYTES", "1048576"))
            cl = request.headers.get("content-length")
            if cl and int(cl) > max_size:
                try:
                    rid = _request_id_ctx.get()
                except Exception:
                    rid = None
                prob = ProblemDetails(
                    type="about:blank",
                    title="Payload Too Large",
                    status=413,
                    detail="Request payload too large",
                    extensions={"correlation_id": rid},
                )
                return JSONResponse(status_code=413, content=prob.model_dump(), media_type="application/problem+json")
        except Exception:
            pass

        return await call_next(request)

    # Small, non-versioned root index
    # Behavior:
    # - If Accept includes application/json (or +json), return a tiny JSON index
    #   enumerating available API versions and helpful links. This is intended
    #   for machine/service discovery and automated checks. Do NOT redirect
    #   JSON clients to /v1/.
    # - If Accept includes text/html or no Accept header is present, redirect
    #   the client to the docs/landing page so browsers go to interactive docs.
    # - This root MUST never contain business logic; it is discoverability-only.

    @app.get("/", include_in_schema=False)
    async def root_index(request: Request):
        accept = (request.headers.get("accept") or "").lower()

        # If the client explicitly prefers JSON (or any +json media type),
        # return a small JSON index. We deliberately avoid redirecting JSON
        # clients to keep / a machine-friendly index.
        if "application/json" in accept or "+json" in accept:
            return JSONResponse(
                status_code=200,
                content={
                    "service": "cineca-agentic-platform",
                    "description": "Service discovery index. Use /v1/ for the canonical API.",
                    "versions": {"v1": "/v1/"},
                    "docs": "/v1/docs" if settings.ENABLE_DOCS else None,
                    "metrics": "/metrics" if settings.PROMETHEUS_METRICS_ENABLED else None,
                },
            )

        # Otherwise (text/html or no Accept), redirect human users to interactive docs
        # Use 302 so browsers perform a normal GET redirect.
        landing = "/docs" if settings.ENABLE_DOCS else "/v1/"
        return RedirectResponse(url=landing, status_code=302)

    # New versioned root (v1)
    @app.get(
        "/v1/",
        response_class=JSONResponse,
        tags=["meta"],
        summary="Root V1",
        description=(
            "**GET /v1/ – API service metadata**\n\n"
            "**Why we need this endpoint:**\n"
            "- **Service discovery**: Clients can find out what version of the API is running without needing prior knowledge.\n"
            "- **Integration testing**: Automated tests can verify the service is responding correctly before running full test suites.\n"
            "- **Documentation access**: Developers can quickly locate the interactive API documentation and metrics endpoints.\n"
            "- **Environment awareness**: Operations teams can confirm which environment (dev, staging, prod) they're working with.\n"
            "- Without this endpoint, clients would have to guess URLs or hardcode configuration, making the API harder to discover and integrate.\n\n"
            "**What it does:**\n"
            "- Returns basic service information: name, version, runtime environment.\n"
            "- Provides links to interactive documentation and metrics endpoints (when enabled).\n"
            "- Useful for service discovery, health inspection, and integration tests.\n\n"
            "**Access:**\n"
            "- Public endpoint (no authentication required).\n"
            "- Anyone can call this to discover the API.\n\n"
            "**Behavior:**\n"
            "- **No caching**: Always returns fresh metadata.\n"
            "- **Environment-aware**: Shows current `APP_ENV` (dev/staging/prod).\n"
            "- **Feature detection**: Links to `/v1/docs` and `/metrics` only when enabled in config.\n\n"
            "**Responses:**\n"
            "- **200 OK**: Returns service metadata JSON.\n\n"
            "**Examples:**\n"
            "```bash\n"
            "# Check API metadata\n"
            "curl https://api.example.com/v1/\n"
            '# → {"service": "cineca-agentic-platform", "version": "0.1.0", "env": "dev", "docs": "/v1/docs", "metrics": "/metrics"}\n'
            "```"
        ),
    )
    async def root_v1():
        return {
            "service": "cineca-agentic-platform",
            "version": "0.1.0",
            "env": os.getenv("APP_ENV", "dev"),
            "docs": "/v1/docs" if settings.ENABLE_DOCS else None,
            "metrics": "/metrics" if settings.PROMETHEUS_METRICS_ENABLED else False,
        }

    # Try to include optional routers if present
    def _try_include(module_path: str, router_name: str = "router", prefix: str = "") -> None:
        with suppress(Exception):
            mod = __import__(module_path, fromlist=[router_name])
            router = getattr(mod, router_name)
            # If this is the auth router, allow runtime gating of demo routes
            if module_path == "src.routers.auth":
                try:
                    from src.config import settings as psettings
                except Exception:
                    psettings = None

                if psettings and not getattr(psettings, "ENABLE_AUTH_DEMO_ROUTES", False):
                    # If demo routes are disabled, include router but strip demo endpoints if present.
                    # The router itself will still be mounted; auth module should use APIRouter.include_in_schema flags
                    app.include_router(router, prefix=prefix)
                else:
                    app.include_router(router, prefix=prefix)
            else:
                app.include_router(router, prefix=prefix)
            # Log the mounted prefix only to avoid duplicated names in logs
            logger.info("Mounted router: %s", prefix or "/")

    # Versioned API mounting (v1) - Ordered according to API specification
    # 1. Meta (already registered as @app.get("/v1/") above)

    # 2. Health
    _try_include("src.routers.health", prefix="/v1/health")

    # 3. Auth
    _try_include("src.routers.auth", prefix="/v1/auth")

    # 4. Tools
    _try_include("src.routers.tools", prefix="/v1/tools")

    # 5. Jobs
    _try_include("src.routers.jobs", prefix="/v1/jobs")

    # 6. Models - User-accessible endpoints (NEW: list, get, test, defaults)
    # Mount model_instances router for regular users at /v1/models (not admin-only)
    _try_include("src.routers.model_instances", prefix="/v1/models")

    # 7. Models - Admin routes (instances, manifests, providers under /v1/admin/models)
    # Admin routes (model instances, jobs, tenants, processes, internal ops)
    # Optionally mount admin/runtime routes under /v1/admin. Default to enabled
    # in developer/test environments so admin-only routes are discoverable
    # unless the operator explicitly disables them.
    if os.getenv("ENABLE_ADMIN_ROUTES", "1") not in ("0", "false", "False"):
        _try_include("src.routers.admin", prefix="/v1/admin")

    # 8. Agents
    _try_include("src.routers.agent", prefix="/v1/agents")
    # Mount the agent-runs router (provides POST /v1/agent-runs)
    try:
        # Import explicitly and log failures so missing routes are visible during startup
        mod = __import__("src.routers.agent_runs", fromlist=["router"])
        router = mod.router
        app.include_router(router, prefix="/v1/agent-runs")
        logger.info("Mounted router: %s", "/v1/agent-runs")
    except Exception:
        logger.exception("Failed to mount router: src.routers.agent_runs")

    # 9. Internal operations
    # We mount internal ops and internal db under separate prefixes so OpenAPI tags
    # can be assigned per-router. internal_ops exposes operational endpoints and
    # internal_db exposes DB job management.
    _try_include("src.routers.internal_ops", prefix="/v1/internal/ops")
    _try_include("src.routers.internal_db", prefix="/v1/internal/db")

    # 10. Admin-facing proxies for internal operations
    # These mirror /internal/* behavior but are gated with require_admin instead of
    # require_internal, allowing platform admins to perform operations without service tokens.
    _try_include("src.routers.admin_ops", prefix="/v1/admin/ops")
    _try_include("src.routers.admin_db", prefix="/v1/admin/db")

    # Batch operations and export/import endpoints
    _try_include("src.routers.batch", prefix="/v1/batch")
    _try_include("src.routers.export_import", prefix="/v1/export")

    # Mount a minimal v2 health surface for previewing v2 docs without changing runtime v1
    _try_include("src.routers.health_v2")  # mounted at /v2/health
    # Admin routes are expected to provide proper GET/HEAD handlers themselves.
    # Temporary ad-hoc HEAD fallback handlers were removed to avoid method shadowing
    # and allow canonical routers (e.g. src.routers.admin_jobs) to control HEAD semantics.

    _mount_metrics(app)

    # Rate limiter (Redis-backed, per-endpoint)
    try:

        # Note: Rate limiting is handled per-endpoint using RateLimitHandler
        # This is called from endpoints when needed, not globally
        logger.info("Rate limit handler available via RateLimitHandler")
    except Exception:
        logger.exception("Failed to initialize rate limiter; continuing without it")

    # Tenant middleware: attach X-Tenant-Id (default to 'global') on request.state
    @app.middleware("http")
    async def tenant_middleware(request, call_next):
        try:
            tenant = request.headers.get("X-Tenant-Id") or "global"
            _tenant_ctx.set(tenant)
            with suppress(Exception):
                request.state.tenant_id = tenant
        except Exception:
            pass
        return await call_next(request)

    # Vary headers middleware: add cache-aware Vary headers
    add_vary_headers(app)

    # Post-process OpenAPI to mark internal endpoints with vendor extension x-internal
    # Mark any operation whose path starts with the internal prefix (e.g. /v1/internal)
    def _mark_x_internal(spec: dict, internal_prefixes: list[str] | str = ("/v1/internal", "/v1/admin")) -> dict:
        try:
            paths = spec.get("paths", {})
            # allow either a single prefix or a list of prefixes
            if isinstance(internal_prefixes, str):
                prefixes = [internal_prefixes]
            else:
                prefixes = list(internal_prefixes)

            for path, methods in list(paths.items()):
                if any(path.startswith(p) for p in prefixes):
                    for _method, info in list(methods.items()):
                        # set a vendor-extension to indicate internal-only operations
                        info.setdefault("x-internal", True)
        except Exception:
            logger.exception("failed to mark x-internal in openapi")
        return spec

    # Ensure ErrorResponse schema is present in components for documentation
    def _inject_error_schema(spec: dict) -> dict:
        try:
            comps = spec.setdefault("components", {})
            schemas = comps.setdefault("schemas", {})
            # ProblemDetails schema (RFC7807)
            if "ProblemDetails" not in schemas:
                schemas["ProblemDetails"] = {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string"},
                        "title": {"type": "string"},
                        "status": {"type": "integer"},
                        "detail": {"type": "string"},
                        "instance": {"type": "string"},
                        "extensions": {"type": "object", "additionalProperties": True, "nullable": True},
                    },
                    "required": ["status"],
                    "example": {
                        "type": "about:blank",
                        "title": "Internal Server Error",
                        "status": 500,
                        "detail": "An unexpected error occurred",
                        "extensions": {"correlation_id": "corr-abc123", "timestamp": "2025-10-20T15:30:45.123456Z"},
                    },
                }
            # Add a reusable response reference under components.responses
            responses = comps.setdefault("responses", {})
            standard_responses = {
                "BadRequest": (400, "Bad Request", "Invalid request parameters or body"),
                "Unauthorized": (401, "Unauthorized", "Missing or invalid authentication token"),
                "Forbidden": (403, "Forbidden", "Authenticated but insufficient permissions"),
                "NotFound": (404, "Not Found", "Requested resource does not exist"),
                "ValidationError": (422, "Validation Error", "Request body failed validation"),
                "TooManyRequests": (429, "Too Many Requests", "Rate limit exceeded"),
                "InternalError": (500, "Internal Server Error", "An unexpected error occurred"),
            }

            for key, (code, title, detail_msg) in standard_responses.items():
                if key not in responses:
                    responses[key] = {
                        "description": title,
                        "content": {
                            "application/problem+json": {
                                "schema": {"$ref": "#/components/schemas/ProblemDetails"},
                                "example": {
                                    "type": f"https://httpstatuses.com/{code}",
                                    "title": title,
                                    "status": code,
                                    "detail": detail_msg,
                                    "extensions": {
                                        "correlation_id": "corr-xyz789",
                                        "timestamp": "2025-10-20T15:30:45.123456Z",
                                    },
                                },
                            }
                        },
                    }

            # Attach default Security Scheme responses? (left to routers to mark auth)

            # Selectively attach standard response refs to operations.
            # - Always add 500 if missing.
            # - Add 401/403 only if operation has a security requirement.
            # - Add 400/422 if operation expects a requestBody or has parameters.
            # - Add 404 if the path contains path parameters.
            paths = spec.get("paths", {})
            for path, methods in list(paths.items()):
                has_path_params = "{" in path and "}" in path
                for _method, info in list(methods.items()):
                    # only for operation objects
                    if not isinstance(info, dict):
                        continue
                    resp = info.setdefault("responses", {})

                    # Always ensure Internal Error (500)
                    if "500" not in resp:
                        resp["500"] = {"$ref": "#/components/responses/InternalError"}

                    # If operation declares security, add 401/403
                    if info.get("security"):
                        if "401" not in resp:
                            resp["401"] = {"$ref": "#/components/responses/Unauthorized"}
                        if "403" not in resp:
                            resp["403"] = {"$ref": "#/components/responses/Forbidden"}

                    # If operation expects a request body or has parameters, add validation errors
                    if info.get("requestBody") or info.get("parameters"):
                        if "400" not in resp:
                            resp["400"] = {"$ref": "#/components/responses/BadRequest"}
                        if "422" not in resp:
                            resp["422"] = {"$ref": "#/components/responses/ValidationError"}

                    # If path contains templated parameters, include NotFound
                    if has_path_params and "404" not in resp:
                        resp["404"] = {"$ref": "#/components/responses/NotFound"}
        except Exception:
            logger.exception("failed to inject ErrorResponse schema")
        return spec

    # Helper to apply common OpenAPI post-processing (error schemas, security, x-internal, tags)
    def _apply_spec_helpers(spec: dict, *, internal_prefixes: list[str] | str = ("/v1/internal", "/v1/admin")) -> dict:
        spec = _inject_error_schema(spec)
        # Do not inject security schemes here — we will strip or expose
        # security at the endpoints that serve OpenAPI JSON as needed.
        spec = _mark_x_internal(spec, internal_prefixes=internal_prefixes)

        # Collect all tags used in operations and create tag metadata
        tags_in_ops = set()
        for _path, methods in spec.get("paths", {}).items():
            for _method, op in methods.items():
                if isinstance(op, dict) and "tags" in op:
                    tags_in_ops.update(op["tags"])

        # Create tag metadata for all tags found in operations
        existing_tags = {t.get("name"): t for t in spec.get("tags", []) if isinstance(t, dict)}
        tag_list = []
        for tag_name in tags_in_ops:
            if tag_name in existing_tags:
                tag_list.append(existing_tags[tag_name])
            else:
                tag_list.append({"name": tag_name})

        # Apply preferred tag ordering
        order_index = {name: i for i, name in enumerate(PREFERRED_TAG_ORDER)}
        spec["tags"] = sorted(tag_list, key=lambda t: order_index.get(t.get("name", ""), 10**6))

        return spec

    def _strip_openapi_security(spec: dict) -> dict:
        """Remove securitySchemes, global security, and operation-level security
            from an OpenAPI spec so the Swagger UI does not render the default
        HTTP bearer block. This lets us keep the custom demo modal while
            removing the built-in authorize block.
        """
        try:
            # remove global schemes and global security requirement
            spec.get("components", {}).pop("securitySchemes", None)
            spec.pop("security", None)

            # remove operation-level security requirements
            for _path, ops in spec.get("paths", {}).items():
                for _method, op in list(ops.items()):
                    if isinstance(op, dict):
                        op.pop("security", None)
        except Exception:
            logger.exception("failed to strip openapi security")
        return spec

    def _inject_security_schemes(spec: dict) -> dict:
        """Ensure a minimal HTTP Bearer (JWT) security scheme exists so the
        Swagger UI presents an Authorize button. This does not force any
        operation to require auth; it merely exposes the HTTP bearer control
        in the UI so users can paste tokens obtained from the demo modal.
        """
        try:
            comps = spec.setdefault("components", {})
            sec = comps.setdefault("securitySchemes", {})

            # Add a minimal HTTPBearer scheme (keeps other schemes removed)
            sec.clear()
            sec["HTTPBearer"] = {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
            }
        except Exception:
            logger.exception("failed to inject security schemes into openapi")
        return spec

    # --- aggregated OpenAPI for /docs (servers dropdown has v1 + v2) ---
    def custom_openapi():
        # honor cached schema
        if getattr(app, "openapi_schema", None):
            return app.openapi_schema
        spec = get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes)
        # For the aggregated UI we present a simple servers dropdown for humans
        spec["servers"] = [{"url": "/{version}", "variables": {"version": {"default": "v1", "enum": ["v1", "v2"]}}}]

        # Do not rewrite or merge prefixed paths; keep them as-is to avoid collisions.
        # Apply helpers and then strip any security so the UI shows only the
        # custom modal (no default HTTP bearer block).
        spec = _apply_spec_helpers(spec, internal_prefixes=["/v1/internal", "/v1/admin"])
        # Inject HTTPBearer and set a global security requirement
        try:
            comps = spec.setdefault("components", {})
            sec = comps.setdefault("securitySchemes", {})
            sec.clear()
            sec["HTTPBearer"] = {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
            spec["security"] = [{"HTTPBearer": []}]
            # Ensure /v1/models* operations explicitly declare security (even if global security later changes)
            try:
                for path, ops in spec.get("paths", {}).items():
                    if path.startswith("/v1/models"):
                        for _method, op in ops.items():
                            if isinstance(op, dict):
                                op.setdefault("security", [{"HTTPBearer": []}])
            except Exception:
                logger.exception("failed to mark models operations as secured")
        except Exception:
            logger.exception("failed to inject HTTPBearer into spec")

        app.openapi_schema = spec
        return spec

    app.openapi = custom_openapi

    # Graceful shutdown: flip readiness to not ready first, allow brief drain
    try:
        import importlib

        health_mod = None
        with suppress(Exception):
            health_mod = importlib.import_module("src.routers.health")

        if health_mod and hasattr(health_mod, "set_ready"):

            async def _on_shutdown():
                with suppress(Exception):
                    health_mod.set_ready(False)

                # Close async Redis client gracefully
                if settings.JOB_STORE_BACKEND.lower() == "redis":
                    try:
                        from db.redis_cache.async_client import close_async_redis

                        await close_async_redis()
                        logger.info("async_redis.shutdown.closed")
                    except Exception:
                        logger.warning("async_redis.shutdown.failed", exc_info=True)

                # allow a configurable drain time for inflight requests
                import asyncio

                try:
                    drain = int(os.getenv("SHUTDOWN_DRAIN_SECONDS", "15"))
                except Exception:
                    drain = 15

                with suppress(Exception):
                    await asyncio.sleep(drain)

            app.add_event_handler("shutdown", _on_shutdown)

            # Ensure readiness is explicitly set to True at startup so TestClient
            # lifecycle (which triggers shutdown handlers) does not leak a
            # 'not ready' state into other tests or app instances.
            async def _on_startup():
                try:
                    # Only set ready if migrations are applied and an operator
                    # hasn't explicitly set the instance to not-ready via admin toggle.
                    enforce = os.getenv("ENFORCE_MIGRATIONS", "0").lower() in ("1", "true", "yes")
                    migrations_ok = True
                    if enforce:
                        migrations_ok = os.getenv("MIGRATIONS_APPLIED", "false").lower() in (
                            "1",
                            "true",
                            "yes",
                        ) or os.path.exists("/app/.migrations_ok")
                    # Read current _is_ready flag from the health module if present
                    current_ready = True
                    try:
                        current_ready = getattr(health_mod, "_is_ready", True)
                    except Exception:
                        current_ready = True

                    if migrations_ok and current_ready:
                        health_mod.set_ready(True)
                except Exception:
                    pass

            app.add_event_handler("startup", _on_startup)

            # Initialize default model and warm up Ollama
            async def _startup_init_default_model():
                """Initialize default model instance and warm up Ollama provider."""
                try:
                    import asyncio
                    from scripts.init_default_model import init_default_model
                    
                    # Run in thread to avoid blocking async event loop
                    await asyncio.to_thread(init_default_model)
                    logger.info("startup.init_default_model.complete")
                except Exception as e:
                    # Non-fatal: log warning but allow app to start
                    logger.warning("startup.init_default_model.failed", extra={"error": str(e)})

            app.add_event_handler("startup", _startup_init_default_model)

            # Async Redis client lifecycle (job storage)
            async def _startup_async_redis():
                """Initialize async Redis client for job storage if needed."""
                if settings.JOB_STORE_BACKEND.lower() == "redis":
                    try:
                        from db.redis_cache.async_client import async_redis_health, get_async_redis

                        # Lazy init will happen on first use, but verify connection
                        await get_async_redis()  # Initialize connection pool
                        health = await async_redis_health()
                        if health.get("ok"):
                            logger.info(
                                "async_redis.startup.connected",
                                extra={
                                    "latency_ms": health.get("latency_ms"),
                                    "backend": settings.JOB_STORE_BACKEND,
                                    "ttl_days": settings.JOB_TTL_DAYS,
                                },
                            )
                        else:
                            logger.warning("async_redis.startup.unhealthy", extra={"error": health.get("error")})
                    except Exception:
                        logger.warning("async_redis.startup.failed", exc_info=True)

            app.add_event_handler("startup", _startup_async_redis)

            # Seed default provider in dev/demo mode (so /providers/main works)
            async def _seed_default_provider():
                """Seed a default provider in dev/demo mode if none exists."""
                # Skip seeding if explicitly disabled via environment variable
                if os.getenv("SEED_DEMO_PROVIDER", "").lower() in ("false", "0", "no"):
                    logger.debug("seed_provider.skip", extra={"reason": "SEED_DEMO_PROVIDER disabled"})
                    return

                if not (settings.DEMO_MODE or settings.APP_ENV == "dev"):
                    return

                try:
                    from db.postgres_control.repositories import provider_repo as pg_repo

                    # Check if a global default already exists
                    try:
                        existing = pg_repo.get_provider_default(scope="global", tenant_id=None)
                        if existing:
                            logger.debug("seed_provider.skip", extra={"reason": "default_exists"})
                            return
                    except Exception:
                        pass  # No default exists, proceed to seed

                    # Check if demo provider already registered
                    providers = pg_repo.list_providers(tenant_id="global")
                    demo_provider = next((p for p in providers if p.get("name") == "demo-openai"), None)

                    if not demo_provider:
                        # Register demo provider
                        demo_provider = pg_repo.create_provider(
                            name="demo-openai",
                            type="openai_compatible",
                            base_url="https://api.openai.com/v1",
                            model="gpt-4",
                            tenant_id="global",
                            config={},
                            actor="system:seed",
                        )
                        logger.info("seed_provider.registered", extra={"provider": "demo-openai"})

                    # Set as global default
                    pg_repo.set_provider_default(
                        scope="global",
                        provider_id=demo_provider.get("id") or demo_provider.get("name"),
                        tenant_id=None,
                        actor="system:seed",
                    )
                    logger.info("seed_provider.default_set", extra={"provider": "demo-openai"})

                except Exception as exc:
                    logger.warning("seed_provider.failed", extra={"error": str(exc)}, exc_info=True)

            app.add_event_handler("startup", _seed_default_provider)

            # Startup provider health check (A.3.1)
            async def _verify_provider_connectivity():
                """Verify default provider is reachable at startup (fail fast if unreachable)."""
                try:
                    from db.postgres_control.repositories import provider_repo as pg_repo
                    from src.background.provider_health import check_provider_health

                    # Get default provider (global scope)
                    default_provider = pg_repo.get_provider_default(scope="global", tenant_id=None)

                    if not default_provider:
                        # Check if any provider exists
                        providers = pg_repo.list_providers(tenant_id=None)
                        if not providers:
                            # No providers at all - this is OK in dev/demo mode
                            if settings.DEMO_MODE or settings.APP_ENV == "dev":
                                logger.info("provider.startup.skip", extra={"reason": "no_providers_in_dev_mode"})
                                return
                            else:
                                logger.warning("provider.startup.no_default", extra={"reason": "no_providers_found"})
                                return
                        # Use first available provider
                        provider_id = providers[0].get("id") or providers[0].get("name")
                        provider = pg_repo.get_provider(provider_id)
                    else:
                        provider_id = default_provider.get("provider_id")
                        provider = pg_repo.get_provider(provider_id)

                    if not provider:
                        logger.warning("provider.startup.not_found", extra={"provider_id": provider_id})
                        return

                    # Perform health check
                    health = await check_provider_health(provider, timeout=5.0)

                    if not health.get("ok"):
                        error_msg = health.get("error", "unknown")
                        logger.error(
                            "provider.startup.unhealthy",
                            extra={
                                "provider_id": provider_id,
                                "provider_name": provider.get("name"),
                                "error": error_msg,
                            },
                        )
                        # In production, fail fast; in dev/demo, continue with warning
                        if not (settings.DEMO_MODE or settings.APP_ENV == "dev"):
                            raise RuntimeError(
                                f"Default provider {provider.get('name')} unhealthy at startup: {error_msg}"
                            )
                        else:
                            logger.warning(
                                "provider.startup.degraded_but_continuing", extra={"provider_id": provider_id}
                            )
                    else:
                        logger.info(
                            "provider.startup.ready",
                            extra={
                                "provider_id": provider_id,
                                "provider_name": provider.get("name"),
                                "status_code": health.get("status_code"),
                            },
                        )
                except RuntimeError:
                    # Re-raise runtime errors (fail fast)
                    raise
                except Exception as exc:
                    logger.warning("provider.startup.check_failed", extra={"error": str(exc)}, exc_info=True)
                    # Don't fail startup, but log prominently

            app.add_event_handler("startup", _verify_provider_connectivity)

            # Model warm-up call (A.3.2 - non-fatal)
            async def _warmup_default_model():
                """Pre-load default model with test inference (non-fatal)."""
                try:
                    from db.postgres_control.repositories import model_instance_repo, provider_repo
                    from src.adapters.llm import LLMClient

                    # Get default model instance (global scope)
                    default = model_instance_repo.get_default(scope="global", tenant_id=None)

                    if not default:
                        logger.debug("model.warmup.skip", extra={"reason": "no_default_model"})
                        return

                    instance_id = getattr(default, "instance_id", None)
                    instance = model_instance_repo.get_instance(instance_id)

                    if not instance or not instance.get("enabled"):
                        logger.debug("model.warmup.skip", extra={"reason": "instance_not_enabled"})
                        return

                    # Get provider for base_url
                    provider_id = instance.get("provider_id")
                    provider = provider_repo.get_provider(provider_id)

                    if not provider:
                        logger.debug("model.warmup.skip", extra={"reason": "provider_not_found"})
                        return

                    base_url = provider.get("base_url")
                    model_id = instance.get("model_id")
                    instance_name = instance.get("instance_name")

                    if not base_url:
                        logger.debug("model.warmup.skip", extra={"reason": "no_base_url"})
                        return

                    # Create LLM client and perform test inference
                    client = LLMClient(model=model_id, api_key=None, base_url=base_url)

                    # Simple test completion with extended timeout for model loading
                    # (First load can take 60-120s for quantized models on CPU, up to 180s on very slow CPUs)
                    # Use LLM_WARMUP_TIMEOUT from settings (default: 300s / 5min)
                    warmup_timeout = getattr(settings, "LLM_WARMUP_TIMEOUT", 300)
                    try:
                        response = await asyncio.wait_for(
                            client.complete(prompt="Test", max_tokens=5, temperature=0), timeout=warmup_timeout
                        )
                        logger.info(
                            "model.warmup.success",
                            extra={
                                "instance_name": instance_name,
                                "model_id": model_id,
                                "response_length": len(str(response)),
                                "timeout_used": warmup_timeout,
                            },
                        )
                    except TimeoutError:
                        logger.warning("model.warmup.timeout", extra={"instance_name": instance_name, "timeout": warmup_timeout})
                    except Exception as warmup_exc:
                        logger.warning(
                            "model.warmup.failed", extra={"instance_name": instance_name, "error": str(warmup_exc)}
                        )
                except Exception as exc:
                    # Non-fatal: warmup failures should not block startup
                    logger.warning("model.warmup.error", extra={"error": str(exc)}, exc_info=True)

            app.add_event_handler("startup", _warmup_default_model)

            # Models repo hydration & sync (providers/instances/defaults)
            try:  # pragma: no cover - startup integration
                from src.repositories import models_repo

                models_repo.hydrate_from_redis()
                models_repo.backfill_to_redis_if_empty()
                models_repo.sync_providers_to_orchestrator()
                logger.info("models_repo.startup.hydrated", extra={"providers": models_repo.provider_count()})
            except Exception:
                logger.warning("models_repo.startup.failed", exc_info=True)

            # Background scheduler (health checks, provider health, etc.)
            # Skip scheduler in test environment or if explicitly disabled
            enable_scheduler = os.getenv("ENABLE_SCHEDULER", "true").lower() not in ("false", "0", "no")
            is_test = os.getenv("APP_ENV") == "test" or os.getenv("PYTEST_CURRENT_TEST")
            
            if enable_scheduler and not is_test:
                async def _startup_scheduler():
                    """Start background scheduler for periodic tasks."""
                    try:
                        from src.background.scheduler import start_scheduler

                        scheduler = start_scheduler()
                        app.state.scheduler = scheduler
                        logger.info("scheduler.startup.started")
                    except Exception as exc:
                        logger.warning("scheduler.startup.failed", extra={"error": str(exc)}, exc_info=True)

                async def _shutdown_scheduler():
                    """Stop background scheduler gracefully."""
                    try:
                        from src.background.scheduler import shutdown_scheduler

                        scheduler = getattr(app.state, "scheduler", None)
                        if scheduler:
                            shutdown_scheduler(wait=True)
                            logger.info("scheduler.shutdown.stopped")
                    except Exception as exc:
                        logger.warning("scheduler.shutdown.failed", extra={"error": str(exc)}, exc_info=True)

                app.add_event_handler("startup", _startup_scheduler)
                app.add_event_handler("shutdown", _shutdown_scheduler)
            else:
                logger.info("scheduler.disabled", reason="test environment" if is_test else "ENABLE_SCHEDULER=false")
    except Exception:
        logger.debug("no health module to flip readiness on shutdown")

    async def _probe_ollama_tags() -> None:
        import logging
        from contextlib import suppress

        try:
            import httpx
        except Exception:
            return

        probe_logger = logging.getLogger("cineca.ollama")

        try:
            from src.repositories import models_repo
        except Exception as exc:
            probe_logger.debug(
                "ollama.probe.skip", extra={"details": {"reason": "models_repo_import_failed", "error": str(exc)}}
            )
            return

        providers: list[dict[str, Any]] = []
        instances: list[dict[str, Any]] = []
        with suppress(Exception):
            providers = [p for p in models_repo.list_providers() if isinstance(p, dict)]
        with suppress(Exception):
            instances = [i for i in models_repo.list_instances() if isinstance(i, dict)]

        ollama_provider_ids = {p.get("id") for p in providers if is_ollama_provider(p)}
        should_probe = bool(ollama_provider_ids) or bool(settings.OLLAMA_BASE_URL)
        if not should_probe:
            return

        selected_provider: dict[str, Any] | None = None
        base_url: str | None = None
        for candidate in providers:
            if not isinstance(candidate, dict):
                continue
            if not is_ollama_provider(candidate):
                continue
            resolved = resolve_provider_base_url(candidate)
            if resolved:
                base_url = resolved
                selected_provider = candidate
                break

        if not base_url:
            base_url = settings.resolve_ollama_base_url()

        # Strip /v1 suffix if present since /api/tags is a native Ollama endpoint
        # (not OpenAI-compatible), while other calls use /v1/chat/completions
        probe_base = base_url.rstrip("/")
        if probe_base.endswith("/v1"):
            probe_base = probe_base[:-3]
        tags_endpoint = probe_base + "/api/tags"

        timeout = timeout_for_provider(selected_provider or {}, default=DEFAULT_HTTPX_TIMEOUT)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                start_time = time.perf_counter()
                resp = await client.get(tags_endpoint)
                latency_ms = int((time.perf_counter() - start_time) * 1000)
            resp.raise_for_status()
        except Exception as exc:
            probe_logger.warning(
                "ollama.probe.failed",
                extra={
                    "details": {
                        "base_url": base_url,
                        "endpoint": tags_endpoint,
                        "provider_id": selected_provider.get("id") if isinstance(selected_provider, dict) else None,
                        "error": str(exc),
                    }
                },
            )
            return

        try:
            payload = resp.json()
        except Exception as exc:
            probe_logger.warning(
                "ollama.probe.invalid_response",
                extra={
                    "details": {
                        "base_url": base_url,
                        "provider_id": selected_provider.get("id") if isinstance(selected_provider, dict) else None,
                        "error": str(exc),
                    }
                },
            )
            return

        models = payload.get("models")
        available_tags: set[str] = set()
        if isinstance(models, list):
            for item in models:
                if not isinstance(item, dict):
                    continue
                for key in ("name", "model", "tag"):
                    value = item.get(key)
                    if isinstance(value, str) and value:
                        available_tags.add(value)

        logical_models: set[str] = set()
        for inst in instances:
            provider_id = inst.get("provider_id")
            if provider_id in ollama_provider_ids:
                with suppress(Exception):
                    model_id = inst.get("model_id") or inst.get("name")
                    if model_id:
                        logical_models.add(str(model_id))

        if not logical_models:
            logical_models = set(settings.effective_ollama_model_map.keys())

        mapped_targets: set[str] = set()
        for logical in logical_models:
            target = settings.effective_ollama_model_map.get(logical)
            mapped_targets.add(target or logical)

        missing = sorted(tag for tag in mapped_targets if tag and tag not in available_tags)

        if missing:
            probe_logger.warning(
                "ollama.probe.missing_models",
                extra={
                    "details": {
                        "base_url": base_url,
                        "provider_id": selected_provider.get("id") if isinstance(selected_provider, dict) else None,
                        "missing": missing,
                        "available": sorted(available_tags),
                    }
                },
            )
        else:
            probe_logger.info(
                "ollama.probe.success",
                extra={
                    "details": {
                        "base_url": base_url,
                        "provider_id": selected_provider.get("id") if isinstance(selected_provider, dict) else None,
                        "latency_ms": latency_ms,
                        "models": sorted(available_tags),
                    }
                },
            )

    app.add_event_handler("startup", _probe_ollama_tags)

    # Register fallback health endpoints if not provided by routers
    def _has_get(path: str) -> bool:
        for r in app.router.routes:
            if getattr(r, "path", None) == path and ("GET" in getattr(r, "methods", [])):
                return True
        return False

    if not _has_get("/health"):

        @app.get("/health", include_in_schema=False)
        async def _health():
            return JSONResponse(status_code=200, content={"status": "ok"})

        @app.head("/health", include_in_schema=False)
        async def _health_head():
            return JSONResponse(status_code=200, content=None)

    if not _has_get("/ready"):

        @app.get("/ready", include_in_schema=False)
        async def _ready():
            return JSONResponse(status_code=200, content={"status": "ready"})

        @app.head("/ready", include_in_schema=False)
        async def _ready_head():
            return JSONResponse(status_code=200, content=None)
    
    # Readiness endpoint: Check if DMR is initialized with database default
    if not _has_get("/readyz"):

        @app.get("/readyz", include_in_schema=False)
        async def _readyz():
            """
            Kubernetes-style readiness probe.
            
            Returns 200 if:
            - App is running (always true if this endpoint responds)
            - Default model is resolved from database (not env var fallback)
            
            Returns 503 if:
            - Default model is falling back to env var (degraded state)
            - DMR service is unavailable
            """
            try:
                from src.services.default_model_resolver import get_default_model_resolver
                dmr = get_default_model_resolver()
                
                # Try to resolve default model
                result = dmr.get_default_model(tenant_id=None, scope="global")
                
                if not result:
                    # No default configured
                    return JSONResponse(
                        status_code=503,
                        content={
                            "status": "not_ready",
                            "reason": "no_default_model_configured"
                        }
                    )
                
                source = result.get("source", "unknown")
                
                if source == "env_var":
                    # Degraded: Falling back to env var
                    return JSONResponse(
                        status_code=503,
                        content={
                            "status": "degraded",
                            "reason": "fallback_to_env_var",
                            "model_id": result.get("model_id")
                        }
                    )
                
                # Healthy: Database resolution
                return JSONResponse(
                    status_code=200,
                    content={
                        "status": "ready",
                        "model_id": result.get("model_id"),
                        "source": source
                    }
                )
                
            except Exception as exc:
                logger.error(f"readyz.check_failed: {exc}", exc_info=True)
                return JSONResponse(
                    status_code=503,
                    content={
                        "status": "error",
                        "reason": str(exc)
                    }
                )

        @app.head("/readyz", include_in_schema=False)
        async def _readyz_head():
            """HEAD version of /readyz - returns same status code without body."""
            try:
                from src.services.default_model_resolver import get_default_model_resolver
                dmr = get_default_model_resolver()
                
                result = dmr.get_default_model(tenant_id=None, scope="global")
                
                if not result:
                    return Response(status_code=503)
                
                source = result.get("source", "unknown")
                
                if source == "env_var":
                    return Response(status_code=503)
                
                return Response(status_code=200)
                
            except Exception:
                return Response(status_code=503)

    # Provide versioned OpenAPI specs even if docs UI is disabled
    def _build_versioned_spec(prefix: str, *, only_paths: list[str] | None = None):
        try:
            spec = get_openapi(
                title=app.title, version=app.version, description=app.description or "", routes=app.routes
            )

            # Keep only paths under the requested prefix and strip the prefix
            filtered: dict = {}
            for path, item in spec.get("paths", {}).items():
                if path == prefix:
                    key = "/"
                elif path.startswith(prefix + "/"):
                    # strip the prefix so the path keys are versionless inside the spec
                    key = path[len(prefix) :]
                else:
                    continue

                if only_paths is not None:
                    candidate = key
                    if candidate not in only_paths and key not in only_paths:
                        continue
                filtered[key] = item

            spec["paths"] = filtered
            # Apply helpers then strip security for UI
            spec = _apply_spec_helpers(spec, internal_prefixes=["/v1/internal", "/v1/admin"])

            # Detect all version prefixes present on app routes and include them in servers
            VERSION_PREFIX_RE = re.compile(r"^/v\d+(?:/|$)")

            def _detect_version_prefixes(app) -> list[str]:
                vers = set()
                for r in app.routes:
                    p = getattr(r, "path", "")
                    m = VERSION_PREFIX_RE.match(p)
                    if not m:
                        continue
                    # capture '/vN' as the prefix
                    parts = p.split("/", 2)
                    if len(parts) >= 2 and parts[1].startswith("v") and parts[1][1:].isdigit():
                        vers.add("/" + parts[1])
                    elif p in ("/v1", "/v2"):
                        vers.add(p)
                return sorted(vers)

            all_versions = _detect_version_prefixes(app)
            # current version first
            servers = [{"url": prefix}]
            for v in all_versions:
                if v != prefix:
                    servers.append({"url": v})
            spec["servers"] = servers
            return spec
        except Exception:
            logger.exception("failed to build versioned spec")
            return {
                "openapi": "3.0.0",
                "info": {"title": app.title, "version": app.version},
                "paths": {},
                "servers": [{"url": prefix}],
            }

    try:

        @app.get("/v1/openapi.json", include_in_schema=False)
        async def openapi_v1():
            spec = _build_versioned_spec("/v1")
            spec.setdefault("servers", [{"url": "/v1"}])
            try:
                comps = spec.setdefault("components", {})
                sec = comps.setdefault("securitySchemes", {})
                sec.clear()
                sec["HTTPBearer"] = {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
                spec["security"] = [{"HTTPBearer": []}]
            except Exception:
                logger.exception("failed to inject HTTPBearer into v1 spec")
            return JSONResponse(spec)

    except Exception:
        logger.exception("failed to mount /v1/openapi.json")

    try:

        @app.get("/v2/openapi.json", include_in_schema=False)
        async def openapi_v2():
            spec = _build_versioned_spec("/v2", only_paths=["/health/live"])  # keep prefixed paths
            spec.setdefault("servers", [{"url": "/v2"}])
            try:
                comps = spec.setdefault("components", {})
                sec = comps.setdefault("securitySchemes", {})
                sec.clear()
                sec["HTTPBearer"] = {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
                spec["security"] = [{"HTTPBearer": []}]
            except Exception:
                logger.exception("failed to inject HTTPBearer into v2 spec")
            return JSONResponse(spec)

    except Exception:
        logger.exception("failed to mount /v2/openapi.json")

        # (versioned spec endpoints already registered above)

        # Expose separate Swagger UIs per version and a single /docs UI that points at v1 by default

        # Provide /v1/metrics alias if Prometheus mounted
        if settings.PROMETHEUS_METRICS_ENABLED:
            try:

                @app.get("/v1/metrics", include_in_schema=False)
                async def metrics_v1():
                    return RedirectResponse(url="/metrics")

            except Exception:
                logger.debug("Failed to mount /v1/metrics")

        # Add HEAD support for v1 health endpoints by delegating to health handlers when available
        # Always add HEAD support for v1 health endpoints by delegating to health handlers when available
        try:
            import importlib

            health_mod = None
            with suppress(Exception):
                health_mod = importlib.import_module("src.routers.health")

            if health_mod:
                if hasattr(health_mod, "health_live"):

                    @app.head("/v1/health/live", include_in_schema=False)
                    async def _head_live():
                        try:
                            await health_mod.health_live()
                            return JSONResponse(status_code=200, content=None)
                        except Exception:
                            return JSONResponse(status_code=500, content=None)

                if hasattr(health_mod, "ready"):

                    @app.head("/v1/health/ready", include_in_schema=False)
                    async def _head_ready():
                        try:
                            res = await health_mod.ready()
                            status_code = getattr(res, "status_code", 200)
                            return JSONResponse(status_code=status_code, content=None)
                        except Exception:
                            return JSONResponse(status_code=500, content=None)

                if hasattr(health_mod, "startup"):

                    @app.head("/v1/health/startup", include_in_schema=False)
                    async def _head_startup():
                        try:
                            res = await health_mod.startup()
                            status_code = getattr(res, "status_code", 200)
                            return JSONResponse(status_code=status_code, content=None)
                        except Exception:
                            return JSONResponse(status_code=500, content=None)

        except Exception:
            logger.exception("failed to add HEAD health handlers")

    # We intentionally do not register /docs. Only /v1/docs and /v2/docs are provided.

    # Prepare minimal UI (version switcher only)
    ver_switch = ""

    def _render_docs(openapi_url: str, title: str, current_version: str) -> HTMLResponse:
        # Render the Swagger UI and inject the version switcher + demo auth UI
        # Control Try it out based on DOCS_AUTH
        submit_methods = (
            []
            if (getattr(settings, "DOCS_AUTH", "internal") == "public")
            else ["get", "post", "put", "delete", "patch", "options", "head"]
        )
        resp = get_swagger_ui_html(
            openapi_url=openapi_url,
            title=title,
            swagger_ui_parameters={"supportedSubmitMethods": submit_methods},
        )
        html = resp.body.decode()
        html = html.replace("<body>", f'<body data-api-version="{current_version}">')
        # ensure both servers appear in the dropdown
        html = html.replace(
            '<select id="servers">',
            '<select id="servers"><option value="/v1">/v1</option><option value="/v2">/v2</option>',
        )
        inject = ver_switch + _REDIRECT_SCRIPT
        html = html.replace("</body>", inject + "</body>")
        return HTMLResponse(content=html)

    # Redirect script injected into versioned Swagger UI pages. It waits for
    # the Servers <select> to be built and binds a change handler that
    # navigates to the matching versioned docs page.
    _REDIRECT_SCRIPT = r"""
<script>
(function () {
    function pickSelector() {
        return document.querySelector('#servers') || document.querySelector('select[aria-label="Servers"]');
    }
    function setDefault(sel) {
        var onV2 = location.pathname.startsWith('/v2/');
        var want = onV2 ? '/v2' : '/v1';
        if (sel && sel.value !== want) sel.value = want;
    }
    function bind() {
        var sel = pickSelector();
        if (!sel) return false;
        if (sel.dataset.bound === '1') return true;
        setDefault(sel);
        sel.addEventListener('change', function () {
            var v = (sel.value || '').replace(/\/+$/, '');
            if (v === '/v2') window.location.href = '/v2/docs';
            else window.location.href = '/v1/docs';
        });
        sel.dataset.bound = '1';
        return true;
    }
    if (!bind()) {
        var mo = new MutationObserver(function () {
            if (bind()) mo.disconnect();
        });
        mo.observe(document.body, { childList: true, subtree: true });
    }
})();
</script>
"""

    # Note: demo request-interceptor removed to avoid auto-injecting Authorization
    # headers into Swagger UI requests. The standard Swagger authorize control
    # will be used if security schemes are present in the OpenAPI spec.
    @app.get("/v1/docs", include_in_schema=False)
    async def docs_v1():
        return _render_docs("/v1/openapi.json", f"{app.title} v1 Docs", "v1")

    @app.get("/v2/docs", include_in_schema=False)
    async def docs_v2():
        return _render_docs("/v2/openapi.json", f"{app.title} v2 Docs", "v2")

    # /docs intentionally absent

    logger.info("App initialized (env=%s, docs_enabled=%s)", os.getenv("APP_ENV", "dev"), settings.ENABLE_DOCS)
    return app


# ASGI application
# Only create app instance at module level if not running under pytest
# (Tests create their own app instances via fixtures)
if not os.getenv("PYTEST_CURRENT_TEST"):
    app = create_app()
