"""
Provider Health Background Scheduler

Periodically refreshes provider health status in the background to prevent
health cache expiration during long-running operations.

Features:
- Configurable refresh interval (default: 1 hour)
- Configurable Redis TTL (default: 2 hours)
- Only runs if SCHEDULER_ENABLED=true
- Graceful degradation on failures
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from src.config import settings

logger = structlog.get_logger(__name__)


class ProviderHealthScheduler:
    """
    Background task to refresh provider health periodically.
    
    Configuration:
    - PROVIDER_HEALTH_REFRESH_INTERVAL: Refresh interval in seconds (default: 3600 / 1 hour)
    - PROVIDER_HEALTH_TTL: Redis cache TTL in seconds (default: 7200 / 2 hours)
    - SCHEDULER_ENABLED: Enable/disable scheduler (default: true)
    
    The TTL should be > refresh interval to prevent gaps in health data.
    """

    def __init__(self):
        self.refresh_interval = getattr(settings, "PROVIDER_HEALTH_REFRESH_INTERVAL", 3600)  # 1 hour
        self.health_ttl = getattr(settings, "PROVIDER_HEALTH_TTL", 7200)  # 2 hours
        self.enabled = getattr(settings, "SCHEDULER_ENABLED", True)
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """Start the background health refresh scheduler."""
        if not self.enabled:
            logger.info(
                "provider_health_scheduler.disabled",
                extra={"reason": "SCHEDULER_ENABLED=false"}
            )
            return

        if self._running:
            logger.warning("provider_health_scheduler.already_running")
            return

        self._running = True
        self._task = asyncio.create_task(self._refresh_loop())
        
        logger.info(
            "provider_health_scheduler.started",
            extra={
                "refresh_interval": self.refresh_interval,
                "health_ttl": self.health_ttl
            }
        )

    async def stop(self) -> None:
        """Stop the background health refresh scheduler."""
        if not self._running:
            return

        self._running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("provider_health_scheduler.stopped")

    async def _refresh_loop(self) -> None:
        """Main refresh loop that runs periodically."""
        while self._running:
            try:
                await asyncio.sleep(self.refresh_interval)
                
                if not self._running:
                    break
                
                logger.debug("provider_health_scheduler.refresh_starting")
                await self._refresh_provider_health()
                logger.debug("provider_health_scheduler.refresh_completed")
                
            except asyncio.CancelledError:
                logger.info("provider_health_scheduler.cancelled")
                break
            except Exception as exc:
                logger.error(
                    f"provider_health_scheduler.refresh_failed: {exc}",
                    exc_info=True
                )
                # Continue loop despite errors

    async def _refresh_provider_health(self) -> None:
        """
        Refresh health status for all providers.
        
        This method probes each provider and updates Redis cache with fresh health data.
        """
        try:
            # Import provider repository (lazy to avoid circular deps)
            from db.postgres_control.repositories import provider_repo
            
            # Get all providers
            providers = provider_repo.list_providers()
            
            if not providers:
                logger.debug("provider_health_scheduler.no_providers")
                return
            
            logger.debug(
                "provider_health_scheduler.probing",
                extra={"provider_count": len(providers)}
            )
            
            # Probe each provider
            for provider in providers:
                try:
                    await self._probe_provider(provider)
                except Exception as exc:
                    logger.warning(
                        f"provider_health_scheduler.probe_failed",
                        extra={
                            "provider_id": provider.get("id"),
                            "error": str(exc)
                        }
                    )
            
        except Exception as exc:
            logger.error(
                f"provider_health_scheduler.refresh_failed: {exc}",
                exc_info=True
            )

    async def _probe_provider(self, provider: dict[str, Any]) -> None:
        """
        Probe a single provider and cache health status.
        
        Args:
            provider: Provider dictionary with id, name, config
        """
        provider_id = provider.get("id")
        provider_name = provider.get("name", "unknown")
        
        try:
            # Try to import health module (lazy to avoid circular deps)
            try:
                from src.health.components import probe_provider_health
            except ImportError:
                logger.debug("provider_health_scheduler.health_module_unavailable")
                return
            
            # Probe provider health
            health_result = await probe_provider_health(provider)
            is_healthy = health_result.get("status") == "ok"
            
            # Cache result in Redis
            try:
                from db.redis_cache.client import cache_set_json
                
                cache_key = f"provider:health:{provider_id}"
                cache_set_json(
                    cache_key,
                    health_result,
                    ex=self.health_ttl
                )
                
                logger.debug(
                    "provider_health.refreshed",
                    extra={
                        "provider_id": provider_id,
                        "provider_name": provider_name,
                        "status": "ok" if is_healthy else "unhealthy",
                        "ttl": self.health_ttl
                    }
                )
                
                # Update Prometheus metric
                try:
                    from src.metrics.prometheus import set_provider_health
                    set_provider_health(
                        provider=provider_id,
                        model_name=provider.get("model", "unknown"),
                        healthy=is_healthy
                    )
                except Exception:
                    pass  # Metrics are optional
                
            except Exception as cache_exc:
                logger.warning(
                    f"provider_health_scheduler.cache_failed: {cache_exc}",
                    extra={"provider_id": provider_id}
                )
                
        except Exception as exc:
            logger.warning(
                f"provider_health_scheduler.probe_failed: {exc}",
                extra={
                    "provider_id": provider_id,
                    "provider_name": provider_name
                },
                exc_info=True
            )


# Singleton instance
_scheduler: ProviderHealthScheduler | None = None


def get_scheduler() -> ProviderHealthScheduler:
    """Get or create singleton ProviderHealthScheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = ProviderHealthScheduler()
    return _scheduler
