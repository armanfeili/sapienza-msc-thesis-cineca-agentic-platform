"""
Background task for provider health checks.

Periodically probes all registered providers and updates their health status in Redis.
This ensures the health endpoint always has fresh provider availability data.

Configuration:
- PROVIDER_HEALTH_CHECK_INTERVAL: int (default: 60 seconds)
- PROVIDER_HEALTH_CHECK_TIMEOUT: float (default: 2.0 seconds)

The health check:
1. Lists all providers from PostgreSQL
2. For each provider, attempts to reach base_url/models (OpenAI-compatible)
3. Updates Redis cache with health status (TTL: 120 seconds)
4. Runs on a schedule (every 60 seconds by default)
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
import structlog

from src.config import settings

log = structlog.get_logger(__name__)


def _get_check_interval() -> int:
    """Get provider health check interval in seconds."""
    try:
        return int(getattr(settings, "PROVIDER_HEALTH_CHECK_INTERVAL", 60))
    except Exception:
        return 60


def _get_check_timeout() -> float:
    """Get provider health check timeout in seconds."""
    try:
        return float(getattr(settings, "PROVIDER_HEALTH_CHECK_TIMEOUT", 2.0))
    except Exception:
        return 2.0


async def check_provider_health(provider: dict[str, Any], timeout: float = 2.0) -> dict[str, Any]:
    """
    Check health of a single provider.

    Args:
        provider: Provider record from database
        timeout: HTTP request timeout in seconds

    Returns:
        Health status dict with keys: ok, status_code?, error?, checked_at
    """
    base_url = provider.get("base_url", "")
    if not base_url:
        return {"ok": False, "error": "no base_url configured", "checked_at": int(time.time())}

    base_url = base_url.rstrip("/")

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            # Try OpenAI-compatible /models endpoint
            response = await client.get(f"{base_url}/models")

            is_healthy = response.status_code == 200
            return {
                "ok": is_healthy,
                "reachable": is_healthy,  # Add reachable field for compatibility with health check
                "status_code": response.status_code,
                "checked_at": int(time.time()),
            }

    except httpx.TimeoutException:
        return {"ok": False, "reachable": False, "error": "timeout", "checked_at": int(time.time())}
    except Exception as exc:
        return {"ok": False, "reachable": False, "error": str(exc), "checked_at": int(time.time())}


async def update_all_provider_health() -> None:
    """
    Update health status for all providers.

    Fetches all providers from PostgreSQL and updates their health in Redis.
    """
    try:
        from db.postgres_control.repositories import provider_repo

        # Get all providers
        providers = await asyncio.to_thread(provider_repo.list_providers, tenant_id=None)

        if not providers:
            log.debug("provider_health.no_providers")
            return

        timeout = _get_check_timeout()
        checked_count = 0
        healthy_count = 0

        # Check each provider
        for provider in providers:
            provider_id = provider.get("id") or provider.get("name")
            if not provider_id:
                continue

            try:
                # Perform health check
                health = await check_provider_health(provider, timeout=timeout)

                # Update Redis cache
                await asyncio.to_thread(provider_repo.set_provider_health, provider_id, health)

                checked_count += 1
                if health.get("ok"):
                    healthy_count += 1

                log.debug(
                    "provider_health.checked",
                    provider_id=provider_id,
                    ok=health.get("ok"),
                    status_code=health.get("status_code"),
                )

            except Exception as exc:
                log.warning("provider_health.check_failed", provider_id=provider_id, error=str(exc))

        log.info(
            "provider_health.update_complete",
            checked=checked_count,
            healthy=healthy_count,
            unhealthy=checked_count - healthy_count,
        )

    except Exception as exc:
        log.error("provider_health.update_failed", error=str(exc))


async def provider_health_loop() -> None:
    """
    Background loop that periodically updates provider health.

    Runs indefinitely until cancelled.
    """
    interval = _get_check_interval()

    log.info("provider_health.loop_started", interval_seconds=interval)

    while True:
        try:
            await update_all_provider_health()
        except Exception as exc:
            log.error("provider_health.loop_error", error=str(exc))

        # Wait for next interval
        await asyncio.sleep(interval)


# Entry point for background scheduler
async def run_provider_health_check() -> None:
    """
    Single execution of provider health update.

    This is called by the background scheduler on a schedule.
    """
    await update_all_provider_health()


__all__ = [
    "check_provider_health",
    "provider_health_loop",
    "run_provider_health_check",
    "update_all_provider_health",
]
