"""
Health & readiness endpoints.

Canonical endpoints:
- GET /health/live       - Liveness probe (plain text)
- GET /health/ready      - Readiness probe (JSON)
- GET /health/startup    - Startup probe with diagnostics (JSON)
- GET /health/components - All component health (JSON)
- GET /health/components/{name} - Single component health (JSON)

This router is mounted at the root path by src.app (no prefix).
"""

from __future__ import annotations

import os
from datetime import datetime

import structlog
from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, PlainTextResponse

from src.config import settings
from src.health import (
    build_response_body,
    evaluate_readiness,
    evaluate_startup,
    get_all_checks,
    get_component_registry,
)

log = structlog.get_logger(__name__)

router = APIRouter(tags=["health"])

# Module-level readiness flag. True when ready, False when not. Defaults to True.
_is_ready = True


def set_ready(v: bool) -> None:
    global _is_ready
    _is_ready = bool(v)


# Versioned health endpoints under /v1/health when mounted with prefix
@router.get(
    "/live",
    response_class=PlainTextResponse,
    include_in_schema=True,
    summary="Liveness probe (canonical)",
    description=(
        "**GET /health/live – Check if the application process is running**\n\n"
        "**Why we need this endpoint:**\n"
        "- **Crash detection**: Container orchestrators (Kubernetes, Docker Swarm) need a quick way to detect if the app has crashed or frozen.\n"
        "- **Automatic restart**: When this endpoint fails, orchestrators automatically restart the container to restore service.\n"
        "- **Resource efficiency**: A fast, lightweight check prevents unnecessary resource usage in monitoring systems.\n"
        "- **Uptime monitoring**: Health monitoring tools use this to track service availability and trigger alerts.\n"
        "- Without this endpoint, orchestrators can't distinguish between a slow app and a crashed one, leading to poor failure recovery.\n\n"
        "**What it does:**\n"
        "- Returns a simple plain-text `ok` string to confirm the process is alive.\n"
        "- Designed for container orchestrators (Kubernetes, Docker, Nomad) to verify the app hasn't crashed.\n"
        "- Performs no external network calls or expensive checks (responds instantly).\n\n"
        "**Access:**\n"
        "- Public endpoint (no authentication required).\n"
        "- Typically called by infrastructure (load balancers, orchestrators).\n\n"
        "**Behavior:**\n"
        "- **Lightweight**: No database queries, no Redis checks, no I/O operations.\n"
        "- **Fast response**: Should respond in <1ms under normal conditions.\n"
        "- **Plain text**: Returns `text/plain` (not JSON) for minimal overhead.\n"
        "- **Always 200**: Never returns errors (if we can run this code, we're alive).\n\n"
        "**Responses:**\n"
        "- **200 OK**: Returns plain text `ok` (process is alive).\n\n"
        "**Examples:**\n"
        "```bash\n"
        "# Check if app is alive\n"
        "curl https://api.example.com/v1/health/live\n"
        "# → ok\n"
        "```"
    ),
    responses={
        200: {
            "content": {"text/plain": {"example": "ok"}},
            "description": "Process is alive",
            "headers": {
                "Cache-Control": {
                    "description": "Prevents caching",
                    "schema": {"type": "string", "example": "no-store"},
                }
            },
        }
    },
)
async def health_live() -> Response:
    """
    Liveness probe: returns simple 'ok' text for low-cost probes.

    This endpoint is intended for orchestration systems to verify the process
    is alive. It performs no external I/O and should be fast and stable.

    Always returns HTTP 200 with plain text "ok" body.
    """
    return PlainTextResponse(content="ok", status_code=200, headers={"Cache-Control": "no-store"})


@router.get(
    "/ready",
    include_in_schema=True,
    summary="Readiness probe (canonical)",
    description=(
        "**GET /health/ready – Check if the service is ready to accept traffic**\n\n"
        "**Why we need this endpoint:**\n"
        "- **Traffic routing**: Load balancers need to know which instances can safely handle requests before sending traffic.\n"
        "- **Graceful deployment**: During deployments, new instances report 'not ready' until dependencies are available, preventing user errors.\n"
        "- **Dependency validation**: Confirms that databases, caches, and other services are reachable before accepting requests.\n"
        "- **Operational control**: Operators can manually mark an instance as 'not ready' for maintenance without killing it.\n"
        "- Without this endpoint, load balancers might send traffic to instances that can't process requests, causing cascading failures and user errors.\n\n"
        "**What it does:**\n"
        "- Performs dependency checks on critical components (PostgreSQL, Redis, Memgraph).\n"
        "- Returns aggregate status: `ok` (ready), `degraded` (partial), or `error` (not ready).\n"
        "- Provides per-dependency details for troubleshooting (connection errors, timeouts, etc.).\n"
        "- Used by load balancers to decide if instance should receive traffic.\n\n"
        "**Access:**\n"
        "- Public endpoint (no authentication required).\n"
        "- Typically called by infrastructure (load balancers, health checkers, deployment tools).\n\n"
        "**Behavior:**\n"
        "- **Dependency checks**: Tests PostgreSQL, Redis, and optional Memgraph connectivity.\n"
        "- **Status aggregation**: `ok` if all pass, `degraded` if some pass, `error` if critical components fail.\n"
        "- **Fallback mode**: When `HEALTH_ALLOW_MG_HEALTH_FALLBACK=1`, missing Memgraph adapter is non-fatal (degraded, not error).\n"
        "- **Admin control**: Readiness can be toggled via admin endpoint (for graceful draining).\n\n"
        "**Responses:**\n"
        "- **200 OK**: Service is ready (all checks passed or degraded with fallback policy).\n"
        "- **503 Service Unavailable**: Service is not ready (critical dependencies failed).\n\n"
        "**Examples:**\n"
        "```bash\n"
        "# Check if service is ready\n"
        "curl https://api.example.com/v1/health/ready\n"
        '# → {"service": "cineca-agentic-platform", "status": "ok", "time": "2025-10-09T12:34:56Z", "checks": {...}}\n\n'
        "# Check when dependencies are down\n"
        "curl https://api.example.com/v1/health/ready\n"
        '# → 503 {"status": "error", "checks": {"postgres": {"ok": false, "error": "connection refused"}, ...}}\n'
        "```"
    ),
    responses={
        200: {
            "description": "Service is ready",
            "content": {
                "application/json": {
                    "example": {
                        "service": "cineca-agentic-platform",
                        "version": "0.1.0",
                        "status": "ok",
                        "time": "2025-10-24T17:01:22.000Z",
                        "checks": {
                            "postgres": {"ok": True, "status": "ok", "latency_ms": 12},
                            "redis": {"ok": True, "status": "ok", "latency_ms": 3},
                        },
                    }
                }
            },
        },
        503: {
            "description": "Service is not ready",
            "content": {
                "application/json": {
                    "example": {
                        "service": "cineca-agentic-platform",
                        "version": "0.1.0",
                        "status": "error",
                        "time": "2025-10-24T17:01:22.000Z",
                        "checks": {
                            "postgres": {"ok": False, "status": "error", "details": {"error": "connection refused"}}
                        },
                    }
                }
            },
        },
    },
)
async def ready() -> Response:
    """
    Readiness probe: checks external dependencies and reports aggregate status.

    Uses the unified component registry to probe all required components
    (app, postgres, redis) and optional components (memgraph, providers, workers).

    Returns:
    - 200 when status is "ok" or "degraded" (with policy)
    - 503 when status is "error" (critical dependencies failed)
    """
    try:
        # Run all component probes
        checks = await get_all_checks()

        # Evaluate readiness policy
        status_str, http_code = evaluate_readiness(checks)

        # Build response body
        body = build_response_body(
            checks=checks,
            status=status_str,
            service_name="cineca-agentic-platform",
            version=getattr(settings, "APP_VERSION", "0.1.0"),
        )

        # Check admin readiness flag
        if not _is_ready:
            body["status"] = "not ready"
            body["reason"] = "admin-disabled"
            return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=body)

        return JSONResponse(status_code=http_code, content=body)

    except Exception as e:
        log.error("health.ready.failed", error=str(e))
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "service": "cineca-agentic-platform",
                "status": "error",
                "time": datetime.utcnow().isoformat() + "Z",
                "error": f"health check failed: {e!s}",
            },
        )


# Ensure HEAD handlers for health endpoints exist (delegates to GET handlers)
@router.head("/live", include_in_schema=False)
async def head_live():
    return PlainTextResponse(status_code=204, content=None)


@router.head("/ready", include_in_schema=False)
async def head_ready():
    # HEAD should be lightweight and return a 2xx/3xx when service is up
    return PlainTextResponse(status_code=204, content=None)


@router.head("/startup", include_in_schema=False)
async def head_startup():
    return PlainTextResponse(status_code=204, content=None)


# ──────────────────────────────────────────────────────────────────────────────
# New Canonical Component Endpoints
# ──────────────────────────────────────────────────────────────────────────────


@router.get(
    "/components",
    include_in_schema=True,
    summary="All components health (canonical)",
    description=(
        "**GET /health/components – List health status of all system components**\n\n"
        "**Why we need this endpoint:**\n"
        "- **Comprehensive monitoring**: See health of all components (databases, caches, queues, observability) in one request.\n"
        "- **Operator dashboard**: Provides complete system snapshot for monitoring dashboards (Grafana, Datadog, etc.).\n"
        "- **Troubleshooting**: Quickly identify which specific components are unhealthy without checking each individually.\n"
        "- **Standardization**: Replaces multiple legacy endpoints (/health/db, /health/redis, etc.) with unified interface.\n"
        "- Without this endpoint, operators need multiple requests to check all system dependencies.\n\n"
        "**What it does:**\n"
        "- Probes all registered components in parallel.\n"
        "- Returns individual status for: app, postgres, redis, memgraph, providers, workers, ollama, prometheus, grafana.\n"
        "- Each component reports: ok, status, latency_ms, details.\n"
        "- Always returns HTTP 200 (reports status even when some components failing).\n\n"
        "**Access:**\n"
        "- Public endpoint (no authentication required).\n"
        "- Typically called by monitoring systems and operator dashboards.\n\n"
        "**Behavior:**\n"
        "- **Parallel probing**: All components checked simultaneously for minimal latency.\n"
        "- **Never fails**: Always returns 200 with individual component statuses.\n"
        "- **Timeout enforcement**: Each probe has hard timeout (200-500ms).\n\n"
        "**Responses:**\n"
        "- **200 OK**: Returns component health summary (even if some failing).\n\n"
        "**Examples:**\n"
        "```bash\n"
        "# Check all components\n"
        "curl https://api.example.com/v1/health/components\n"
        '# → {"service": "...", "checks": {"postgres": {...}, "redis": {...}, ...}}\n'
        "```"
    ),
    responses={
        200: {
            "description": "Component health summary",
            "content": {
                "application/json": {
                    "example": {
                        "service": "cineca-agentic-platform",
                        "version": "0.1.0",
                        "status": "ok",
                        "time": "2025-10-24T17:01:22.000Z",
                        "checks": {
                            "postgres": {"ok": True, "status": "ok", "latency_ms": 12},
                            "redis": {"ok": True, "status": "ok", "latency_ms": 3},
                            "memgraph": {"ok": True, "status": "unknown", "details": {"reason": "adapter-missing"}},
                            "providers": {"ok": True, "status": "ok", "latency_ms": 45},
                        },
                    }
                }
            },
        }
    },
)
async def get_all_components() -> Response:
    """
    Get health status of all system components.

    Always returns 200 with individual component statuses,
    regardless of overall system health.
    """
    try:
        checks = await get_all_checks()

        # Determine overall status for informational purposes
        status_str, _ = evaluate_readiness(checks)

        body = build_response_body(
            checks=checks,
            status=status_str,
            service_name="cineca-agentic-platform",
            version=getattr(settings, "APP_VERSION", "0.1.0"),
        )

        return JSONResponse(status_code=200, content=body)

    except Exception as e:
        log.error("health.components.failed", error=str(e))
        return JSONResponse(
            status_code=200,  # Still return 200 even on error
            content={
                "service": "cineca-agentic-platform",
                "status": "error",
                "time": datetime.utcnow().isoformat() + "Z",
                "error": f"component check failed: {e!s}",
                "checks": {},
            },
        )


@router.get(
    "/components/{name}",
    include_in_schema=True,
    summary="Single component health (canonical)",
    description=(
        "**GET /health/components/{name} – Check health of a single component**\n\n"
        "**Why we need this endpoint:**\n"
        "- **Focused monitoring**: Check specific component without querying all dependencies.\n"
        "- **Alert targeting**: Monitoring systems can create component-specific alerts.\n"
        "- **Debugging**: Quickly verify if a specific component is the root cause of issues.\n"
        "- **Performance**: Faster than /health/components when only one component matters.\n"
        "- Without this endpoint, monitoring systems must parse full component list for single checks.\n\n"
        "**What it does:**\n"
        "- Probes a single component by name.\n"
        "- Returns: ok, status, latency_ms, details.\n"
        "- Available components: app, postgres, redis, memgraph, providers, workers, ollama, prometheus, grafana.\n"
        "- Always returns HTTP 200 (reports status even if component failing).\n\n"
        "**Access:**\n"
        "- Public endpoint (no authentication required).\n"
        "- Typically called by monitoring systems for component-specific checks.\n\n"
        "**Behavior:**\n"
        "- **Single probe**: Only checks requested component.\n"
        "- **Never fails**: Always returns 200 with component status.\n"
        "- **Timeout enforcement**: Probe has hard timeout (200-500ms).\n"
        "- **Unknown components**: Returns error status if component name invalid.\n\n"
        "**Responses:**\n"
        "- **200 OK**: Returns component health (even if component failing).\n\n"
        "**Examples:**\n"
        "```bash\n"
        "# Check PostgreSQL\n"
        "curl https://api.example.com/v1/health/components/postgres\n"
        '# → {"ok": true, "status": "ok", "latency_ms": 12}\n\n'
        "# Check Redis\n"
        "curl https://api.example.com/v1/health/components/redis\n"
        '# → {"ok": true, "status": "ok", "latency_ms": 3, "details": {"queues": {...}}}\n'
        "```"
    ),
    responses={
        200: {
            "description": "Component health status",
            "content": {
                "application/json": {
                    "example": {"ok": True, "status": "ok", "latency_ms": 12, "details": {"database": "postgresql"}}
                }
            },
        }
    },
)
async def get_single_component(name: str) -> Response:
    """
    Get health status of a single component.

    Always returns 200 with component status,
    regardless of whether component is healthy.
    """
    try:
        registry = get_component_registry()
        check = await registry.probe(name)

        return JSONResponse(status_code=200, content=check.to_dict())

    except Exception as e:
        log.error("health.component.failed", component=name, error=str(e))
        return JSONResponse(
            status_code=200, content={"ok": False, "status": "error", "details": {"error": f"probe failed: {e!s}"}}
        )


# ──────────────────────────────────────────────────────────────────────────────
# Deprecated Endpoints (serve with deprecation headers)
# ──────────────────────────────────────────────────────────────────────────────


@router.get(
    "/startup",
    include_in_schema=True,
    summary="Startup check (canonical, with diagnostics)",
    description=(
        "**GET /health/startup – Diagnostic startup health check**\n\n"
        "**Why we need this endpoint:**\n"
        "- **Deployment validation**: CI/CD pipelines need to verify all dependencies are available before declaring a deployment successful.\n"
        "- **Troubleshooting**: When deployments fail, this endpoint provides detailed error messages showing exactly which dependency is unavailable.\n"
        "- **Migration verification**: Confirms that database migrations have completed before accepting traffic.\n"
        "- **Rate limit validation**: Verifies rate limiting is configured correctly (e.g., RATE_LIMIT_MODE=prod in production).\n"
        "- **Semantic clarity**: Distinguishes startup checks (one-time validation) from ongoing readiness checks (continuous monitoring).\n"
        "- Without this endpoint, deployment scripts would have to guess whether failures are temporary (retry) or permanent (rollback), leading to longer outages.\n\n"
        "**What it does:**\n"
        "- Returns comprehensive health information including all readiness checks.\n"
        "- **Includes**: Rate limit configuration diagnostics (mode, backend, limits).\n"
        "- **Includes**: Migration state and enforcement policy.\n"
        "- **Includes**: Environment diagnostics.\n"
        "- Surfaces detailed dependency errors for troubleshooting during provisioning.\n"
        "- Intended for deployment automation and troubleshooting.\n\n"
        "**Access:**\n"
        "- Public endpoint (no authentication required).\n"
        "- Typically called by deployment tooling (CI/CD, provisioning scripts).\n\n"
        "**Behavior:**\n"
        "- **All readiness checks**: Tests PostgreSQL, Redis, Memgraph, providers, workers.\n"
        "- **Rate limit config**: Reports current RATE_LIMIT_MODE and actual rate limit values.\n"
        "- **Migration verification**: Confirms migrations applied if ENFORCE_MIGRATIONS=1.\n"
        "- **Production validation**: Verifies RATE_LIMIT_MODE is 'prod' (not 'test') in production.\n\n"
        "**Responses:**\n"
        "- **200 OK**: Service dependencies are healthy (ready for traffic).\n"
        "- **503 Service Unavailable**: Dependencies failed or not ready (deployment should retry).\n\n"
        "**Examples:**\n"
        "```bash\n"
        "# Check startup health during deployment\n"
        "curl https://api.example.com/v1/health/startup\n"
        '# → {"service": "cineca-agentic-platform", "status": "ok", "environment": {"rate_limit_mode": "prod", ...}, ...}\n\n'
        "# Diagnose startup failures\n"
        "curl https://api.example.com/v1/health/startup\n"
        '# → 503 {"status": "error", "environment": {...}, "checks": {...}, "migrations": {"required": true, "applied": false}}\n'
        "```"
    ),
    responses={
        200: {
            "description": "Service is ready for startup",
            "content": {
                "application/json": {
                    "example": {
                        "service": "cineca-agentic-platform",
                        "version": "0.1.0",
                        "status": "ok",
                        "time": "2025-10-24T17:01:22.000Z",
                        "checks": {"postgres": {"ok": True, "status": "ok"}},
                        "environment": {"rate_limit_mode": "prod", "rate_limit_backend": "redis"},
                        "limits": {"tools:invoke": 5},
                        "migrations": {"required": True, "applied": True},
                    }
                }
            },
        },
        503: {
            "description": "Service is not ready",
            "content": {
                "application/json": {
                    "example": {
                        "service": "cineca-agentic-platform",
                        "version": "0.1.0",
                        "status": "error",
                        "time": "2025-10-24T17:01:22.000Z",
                        "checks": {"postgres": {"ok": False, "status": "error"}},
                        "migrations": {"required": True, "applied": False},
                    }
                }
            },
        },
    },
)
async def startup() -> Response:
    """
    Startup endpoint with rich diagnostics.

    Returns same structure as /ready but with additional environment,
    limits, and migrations blocks for deployment troubleshooting.

    Stricter than /ready: enforces migration requirements and validates
    rate limit configuration.
    """
    try:
        # Run all component probes
        checks = await get_all_checks()

        # Evaluate startup policy (includes readiness + migrations + rate limits)
        status_str, http_code, extras = evaluate_startup(checks)

        # Build response body with extras
        body = build_response_body(
            checks=checks,
            status=status_str,
            service_name="cineca-agentic-platform",
            version=getattr(settings, "APP_VERSION", "0.1.0"),
            extras=extras,
        )

        return JSONResponse(status_code=http_code, content=body)

    except Exception as e:
        log.error("health.startup.failed", error=str(e))
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "service": "cineca-agentic-platform",
                "status": "error",
                "time": datetime.utcnow().isoformat() + "Z",
                "error": f"health check failed: {e!s}",
            },
        )


# Admin API: allow toggling readiness (useful for deployments). Register the
# admin readiness toggle endpoint unconditionally so tests and operators can
# toggle readiness via /v1/health/startup/readiness when authorized. The
# endpoint itself enforces admin authentication via X-Admin-Token or admin JWT.
import structlog
from fastapi import Depends

from src.routers.auth import get_current_user  # noqa: F401 (import used in deps)

log = structlog.get_logger(__name__)

from src.security.jwt import validate_jwt

# Export whether admin routes are enabled so unit tests can inspect this flag.
# Default to enabled unless environment explicitly disables it.
_enable_admin = os.getenv("ENABLE_ADMIN_ROUTES", "1") not in ("0", "false", "False")


async def _require_admin(
    request: Request, x_admin_token: str | None = Header(None, convert_underscores=False, alias="X-Admin-Token")
) -> dict | None:
    """Authenticate admin caller.

    Priority:
     - If ADMIN_TOKEN env var is set, require X-Admin-Token equal to it.
     - Otherwise require a valid JWT Bearer token with 'admin' in scopes.
    Returns a dict with actor info when authorized, else raises HTTPException.
    """
    admin_token = os.getenv("ADMIN_TOKEN")
    # If shared admin token is configured, prefer it
    if admin_token:
        if not x_admin_token:
            raise HTTPException(status_code=401, detail="admin token required")
        if x_admin_token != admin_token:
            raise HTTPException(status_code=403, detail="invalid admin token")
        return {"actor": "admin-token"}

    # Fall back to JWT-based admin check: parse Authorization header
    auth = request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="authentication required")
    token = auth.split(None, 1)[1]
    try:
        payload = await validate_jwt(token)
    except Exception:
        raise HTTPException(status_code=401, detail="invalid token")
    scopes = []
    try:
        if isinstance(payload, dict):
            if "scope" in payload and isinstance(payload["scope"], str):
                scopes = [s for s in payload["scope"].split() if s]
            elif isinstance(payload.get("scopes"), list):
                scopes = [str(x) for x in payload.get("scopes")]
            elif isinstance(payload.get("roles"), list):
                scopes = [str(x) for x in payload.get("roles")]
    except Exception:
        scopes = []
    if "admin" not in scopes:
        raise HTTPException(status_code=403, detail="admin scope required")
    return {"actor": (payload.get("sub") if isinstance(payload, dict) else "admin") or "admin"}


@router.post("/startup/readiness", include_in_schema=False)
async def set_startup_readiness(state: str, request: Request, auth=Depends(_require_admin)) -> Response:
    """Set readiness state for this instance. Accepts 'ready' or 'not-ready'.

    This endpoint is intended for operators during rolling updates to mark an
    instance as not-ready before draining traffic. Calls are audited.
    """
    reason = request.query_params.get("reason") or request.headers.get("X-Admin-Reason")
    actor = (auth and auth.get("actor")) or (
        request.headers.get("X-Admin-Actor") or (request.client.host if getattr(request, "client", None) else "admin")
    )
    old = bool(_is_ready)
    val = (state or "").strip().lower()

    if val == "ready":
        set_ready(True)
        new = True
        log.info("readiness.toggled", actor=actor, old=old, new=new, reason=reason)
        return JSONResponse(status_code=200, content={"status": "ready"})

    if val in {"not-ready", "not_ready", "notready"}:
        set_ready(False)
        new = False
        log.info("readiness.toggled", actor=actor, old=old, new=new, reason=reason)
        return JSONResponse(status_code=200, content={"status": "not ready"})

    raise HTTPException(status_code=400, detail="invalid state; use 'ready' or 'not-ready'")


@router.get(
    "/config",
    include_in_schema=True,
    summary="System configuration details",
    description=(
        "**GET /health/config – View compute configuration and system settings**\n\n"
        "Provides detailed information about the current system configuration,\n"
        "including compute device, timeout settings, model selection, and more.\n\n"
        "**Access:**\n"
        "- Public endpoint (no authentication required).\n\n"
        "**Responses:**\n"
        "- **200 OK**: Returns system configuration.\n"
    ),
    responses={
        200: {
            "description": "System configuration",
            "content": {
                "application/json": {
                    "example": {
                        "service": "cineca-agentic-platform",
                        "version": "0.1.0",
                        "compute": {
                            "device": "cpu",
                            "max_concurrent_llm_calls": 1,
                            "timeouts": {
                                "step_seconds": 120,
                                "run_seconds": 300
                            },
                            "models": {
                                "plan_model": "phi3:mini",
                                "warmup_models": ["phi3:mini"]
                            }
                        }
                    }
                }
            },
        }
    },
)
async def get_config() -> Response:
    """
    Get system configuration details.
    
    Includes compute configuration, timeout settings, and model selection.
    """
    try:
        from src.config_modules.compute import get_compute_config
        compute_cfg = get_compute_config()
        
        body = {
            "service": "cineca-agentic-platform",
            "version": getattr(settings, "APP_VERSION", "0.1.0"),
            "time": datetime.utcnow().isoformat() + "Z",
            "compute": {
                "device": compute_cfg.device,
                "max_concurrent_llm_calls": compute_cfg.max_concurrent_llm_calls,
                "timeouts": {
                    "step_seconds": compute_cfg.step_timeout_seconds,
                    "run_seconds": compute_cfg.run_timeout_seconds,
                },
                "models": {
                    "plan_model": compute_cfg.plan_model_name,
                    "execute_model": compute_cfg.execute_model_name,
                    "warmup_models": compute_cfg.warmup_models,
                },
                "test_mode": compute_cfg.test_mode,
                "recommended": {
                    "step_timeout": compute_cfg.recommended_step_timeout,
                    "run_timeout": compute_cfg.recommended_run_timeout,
                    "concurrency": compute_cfg.recommended_concurrency,
                }
            }
        }
        
        return JSONResponse(status_code=200, content=body)
    
    except Exception as e:
        log.error("health.config.failed", error=str(e))
        return JSONResponse(
            status_code=200,
            content={
                "service": "cineca-agentic-platform",
                "status": "error",
                "time": datetime.utcnow().isoformat() + "Z",
                "error": f"config retrieval failed: {e!s}",
            },
        )
