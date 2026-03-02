"""
Policy evaluation for readiness and startup checks.

Implements logic to aggregate component checks into overall service status based on:
- Required vs optional components
- Degraded tolerance policies
- Migration enforcement
- Rate limit validation
"""

import os
from datetime import datetime
from typing import Any

import structlog

from src.health.components import ComponentCheck, ComponentStatus, get_component_registry
from src.health.config import get_health_config

log = structlog.get_logger(__name__)


def evaluate_readiness(checks: dict[str, ComponentCheck]) -> tuple[str, int]:
    """
    Evaluate readiness based on component checks.

    Returns:
        Tuple of (status, http_code) where:
        - status is "ok", "degraded", or "error"
        - http_code is 200 for ok/degraded (with policy), 503 for error

    Policy:
    - Required components (app, postgres, redis) must be ok or degraded (with fallback)
    - Optional components (memgraph, providers, workers) can be degraded without failing readiness
    - Informational components (ollama, prometheus, grafana) don't affect readiness
    """
    config = get_health_config()

    # Check required components
    required_ok = True
    has_degraded = False

    for name, check in checks.items():
        is_required = name in config.required_components

        if is_required:
            if check.status == ComponentStatus.ERROR:
                required_ok = False
            elif check.status == ComponentStatus.DEGRADED:
                has_degraded = True
            elif check.status == ComponentStatus.UNKNOWN:
                # Unknown is acceptable for required components only if fallback enabled
                if (name == "memgraph" and config.allow_mg_health_fallback) or (name == "redis" and config.allow_redis_health_fallback):
                    has_degraded = True
                else:
                    required_ok = False
        # Optional/informational components can be degraded or unknown
        elif check.status in (ComponentStatus.DEGRADED, ComponentStatus.UNKNOWN, ComponentStatus.ERROR):
            has_degraded = True

    # Determine overall status
    if not required_ok:
        return ("error", 503)
    elif has_degraded:
        # Degraded is acceptable if policy allows
        if config.allow_degraded:
            return ("degraded", 200)
        else:
            return ("error", 503)
    else:
        return ("ok", 200)


def evaluate_startup(checks: dict[str, ComponentCheck]) -> tuple[str, int, dict[str, Any]]:
    """
    Evaluate startup readiness (stricter than runtime readiness).

    Returns:
        Tuple of (status, http_code, extras) where:
        - status is "ok", "degraded", or "error"
        - http_code is 200 for ok/degraded, 503 for error
        - extras contains environment, limits, migrations blocks

    Policy:
    - All readiness requirements must pass
    - Migrations must be applied if ENFORCE_MIGRATIONS=1
    - Rate limiter mode validation (warn if not "prod" in production)
    - Environment diagnostics included
    """
    config = get_health_config()

    # Start with readiness evaluation
    status, http_code = evaluate_readiness(checks)

    # Check migrations
    migrations_applied = False

    if config.enforce_migrations:
        # Check if migrations marker file exists or env var set
        migrations_applied = os.path.exists("/app/.migrations_ok") or os.getenv(
            "MIGRATIONS_APPLIED", "false"
        ).lower() in ("1", "true", "yes")
        if not migrations_applied:
            status = "error"
            http_code = 503
            log.warning("health.startup.migrations_not_applied")

    # Build environment block
    try:
        from db.redis_cache.rate_limit import RATE_LIMIT_MODE, _get_rate_limits

        rate_limit_backend = getattr(__import__("src.config").config.settings, "RATE_LIMIT_BACKEND", "redis")
    except Exception:
        RATE_LIMIT_MODE = "test"
        rate_limit_backend = "redis"

    environment: dict[str, Any] = {
        "rate_limit_mode": RATE_LIMIT_MODE,
        "rate_limit_backend": rate_limit_backend,
    }

    # Warn if rate limit mode is not "prod" in production environments
    if os.getenv("ENV", "dev") == "prod" and RATE_LIMIT_MODE != "prod":
        log.warning("health.startup.rate_limit_mode_mismatch", env="prod", rate_limit_mode=RATE_LIMIT_MODE)

    # Build limits block
    limits: dict[str, Any] = {}
    try:
        from db.redis_cache.rate_limit import _get_rate_limits

        rate_configs = _get_rate_limits()
        for action, cfg in rate_configs.items():
            if isinstance(cfg, dict):
                limits[action] = cfg.get("limit", 0)
    except Exception as e:
        log.warning("health.startup.rate_limits_unavailable", error=str(e))

    # Build migrations block
    migrations: dict[str, Any] = {
        "required": config.enforce_migrations,
        "applied": migrations_applied if config.enforce_migrations else None,
    }

    # Build extras
    extras: dict[str, Any] = {
        "environment": environment,
        "limits": limits,
        "migrations": migrations,
    }

    return (status, http_code, extras)


async def get_all_checks() -> dict[str, ComponentCheck]:
    """
    Run all component probes and return results.

    This is a convenience wrapper around the component registry.
    """
    registry = get_component_registry()
    return await registry.probe_all()


def build_response_body(
    checks: dict[str, ComponentCheck],
    status: str,
    service_name: str = "cineca-agentic-platform",
    version: str = "0.1.0",
    instance_id: str | None = None,
    extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build standardized health response body.

    Args:
        checks: Component check results
        status: Overall status ("ok", "degraded", "error")
        service_name: Service name
        version: Service version
        instance_id: Optional instance identifier
        extras: Optional extra fields (environment, limits, migrations)

    Returns:
        JSON-serializable dictionary
    """
    body: dict[str, Any] = {
        "service": service_name,
        "version": version,
        "status": status,
        "time": datetime.utcnow().isoformat() + "Z",
        "checks": {name: check.to_dict() for name, check in checks.items()},
    }

    if instance_id:
        body["instance_id"] = instance_id

    if extras:
        body.update(extras)

    return body
