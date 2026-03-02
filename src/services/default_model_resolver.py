"""
Default Model Resolver (DMR) - Single source of truth for default model resolution.

This service centralizes how the platform determines the current default model,
with PostgreSQL as the authoritative source, Redis caching for performance,
and environment variable fallback for resilience.

Architecture:
1. Check Redis cache (fast path ~1ms)
2. Query PostgreSQL (authoritative source ~10ms)
3. Cache result in Redis (TTL: 15 min)
4. Fallback to env var only if DB unreachable (degraded mode)

Usage:
    from src.services.default_model_resolver import get_dmr
    
    dmr = get_dmr()
    default = await dmr.get_default_model(tenant_id=None)
    # Returns: {
    #   "model_id": "phi3:mini",
    #   "provider_model_id": "phi3:mini",
    #   "instance_id": "abc-123",
    #   "instance_name": "phi3-mini",
    #   "provider_id": "xyz-789",
    #   "provider_name": "Local Ollama",
    #   "base_url": "http://ollama:11434/v1",
    #   "config_source": "db_default",
    #   "source": "db",  # or "redis", "env_fallback"
    #   "cached": True
    # }
"""

from __future__ import annotations

import logging
import time
from typing import Any

from src.config import settings
from src.models.llm_config import LLMModelConfig

logger = logging.getLogger(__name__)


class DefaultModelResolver:
    """
    Resolves the default model for API requests, orchestrator, health checks, etc.
    
    Thread-safe singleton pattern with lazy initialization.
    """
    
    _instance: DefaultModelResolver | None = None
    _initialized: bool = False
    
    def __new__(cls) -> DefaultModelResolver:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize DMR (idempotent - can be called multiple times)."""
        if DefaultModelResolver._initialized:
            return
        
        self.cache_ttl = getattr(settings, "DEFAULT_MODEL_CACHE_TTL_SECONDS", 900)  # 15 min
        self.allow_env_fallback = getattr(settings, "DEFAULT_MODEL_ALLOW_ENV_FALLBACK", True)
        
        DefaultModelResolver._initialized = True
        
        logger.info("dmr.initialized", extra={
            "cache_ttl": self.cache_ttl,
            "allow_env_fallback": self.allow_env_fallback
        })
    
    async def get_default_model(
        self, 
        tenant_id: str | None = None,
        scope: str = "global"
    ) -> dict[str, Any] | None:
        """
        Resolve the default model with caching and fallback.
        
        Resolution order:
        1. Redis cache (if hit)
        2. PostgreSQL (authoritative)
        3. Environment variable (emergency fallback)
        
        Args:
            tenant_id: Tenant ID for tenant-scoped defaults (None = global)
            scope: Scope for resolution ("global" or "tenant")
            
        Returns:
            dict with keys: model_id, instance_id, provider_id, source, cached
            None if no default configured and fallback disabled
            
        Raises:
            No exceptions raised - returns None or fallback on errors
        """
        start_time = time.time()
        
        # 1. Try Redis cache (fast path)
        cache_key = self._build_cache_key(scope, tenant_id)
        cached_result = await self._get_from_cache(cache_key)
        
        if cached_result:
            cached_result["source"] = "redis"
            cached_result["cached"] = True
            elapsed_ms = (time.time() - start_time) * 1000
            logger.info("model.default.resolved", extra={
                "model_id": cached_result.get("model_id"),
                "instance_id": cached_result.get("instance_id"),
                "provider_id": cached_result.get("provider_id"),
                "source": "redis",
                "cached": True,
                "tenant_id": tenant_id or "global",
                "scope": scope,
                "latency_ms": round(elapsed_ms, 2)
            })
            
            # Record cache hit
            await self._record_cache_hit(tenant_id)
            
            return cached_result
        
        # Cache miss - record it
        await self._record_cache_miss(tenant_id)
        
        # 2. Query PostgreSQL (authoritative source)
        db_result = await self._get_from_db(scope, tenant_id)
        
        if db_result:
            # Cache the result
            await self._set_cache(cache_key, db_result)
            
            elapsed_ms = (time.time() - start_time) * 1000
            logger.info("model.default.resolved", extra={
                "model_id": db_result.get("model_id"),
                "instance_id": db_result.get("instance_id"),
                "provider_id": db_result.get("provider_id"),
                "source": "db",
                "cached": False,
                "tenant_id": tenant_id or "global",
                "scope": scope,
                "latency_ms": round(elapsed_ms, 2)
            })
            
            return db_result
        
        # 3. Fallback to environment variable (degraded mode)
        if self.allow_env_fallback and settings.DEFAULT_MODEL_NAME:
            elapsed_ms = (time.time() - start_time) * 1000
            
            logger.warning("model.default.env_fallback", extra={
                "model_id": settings.DEFAULT_MODEL_NAME,
                "reason": "db_no_default_configured",
                "tenant_id": tenant_id or "global",
                "scope": scope,
                "latency_ms": round(elapsed_ms, 2)
            })
            
            # Mark health as degraded
            try:
                from src.health import health as health_mod
                health_mod.set_degraded(reason="default_model_source=env_fallback")
            except Exception:
                logger.debug("dmr: failed to set health degraded", exc_info=True)
            
            return {
                "model_id": settings.DEFAULT_MODEL_NAME,
                "provider_model_id": settings.DEFAULT_MODEL_NAME,
                "instance_id": None,
                "instance_name": settings.DEFAULT_MODEL_NAME,
                "provider_id": None,
                "provider_name": None,
                "base_url": getattr(settings, "DEFAULT_MODEL_BASE_URL", None),
                "config_source": "env_fallback",
                "source": "env_fallback",
                "cached": False
            }
        
        # No default found
        elapsed_ms = (time.time() - start_time) * 1000
        logger.warning("model.default.not_found", extra={
            "tenant_id": tenant_id or "global",
            "scope": scope,
            "latency_ms": round(elapsed_ms, 2)
        })
        
        return None
    
    async def invalidate_cache(
        self,
        scope: str = "global",
        tenant_id: str | None = None,
        reason: str = "explicit_invalidation"
    ) -> bool:
        """
        Invalidate the cached default model.
        
        Call this after PATCH /models/defaults or when default changes.
        
        Args:
            scope: Scope to invalidate ("global" or "tenant")
            tenant_id: Tenant ID for tenant-scoped invalidation
            reason: Reason for invalidation (for logging)
            
        Returns:
            True if cache was invalidated, False otherwise
        """
        cache_key = self._build_cache_key(scope, tenant_id)
        
        try:
            # Try to get Redis client
            from db.redis_cache.client import get_redis, redis_available
            
            if not redis_available():
                logger.debug("dmr.cache_invalidation_skipped", extra={
                    "reason": "redis_unavailable"
                })
                return False
            
            redis = get_redis()
            deleted = redis.delete(cache_key)
            
            logger.info("model.default.cache_invalidated", extra={
                "scope": scope,
                "tenant_id": tenant_id or "global",
                "reason": reason,
                "cache_key": cache_key,
                "deleted": bool(deleted)
            })
            
            return bool(deleted)
            
        except Exception as e:
            logger.warning("dmr.cache_invalidation_failed", extra={
                "error": str(e),
                "scope": scope,
                "tenant_id": tenant_id or "global"
            })
            return False
    
    async def warmup_cache(
        self,
        tenant_id: str | None = None,
        scope: str = "global"
    ) -> bool:
        """
        Pre-populate Redis cache with default model.
        
        Call this on startup or after cache invalidation to warm the cache.
        
        Args:
            tenant_id: Tenant ID for tenant-scoped warmup
            scope: Scope to warm ("global" or "tenant")
            
        Returns:
            True if cache was warmed, False otherwise
        """
        try:
            result = await self.get_default_model(tenant_id=tenant_id, scope=scope)
            
            if result:
                logger.info("dmr.cache_warmed", extra={
                    "scope": scope,
                    "tenant_id": tenant_id or "global",
                    "model_id": result.get("model_id"),
                    "source": result.get("source")
                })
                return True
            
            return False
            
        except Exception as e:
            logger.warning("dmr.cache_warmup_failed", extra={
                "error": str(e),
                "scope": scope,
                "tenant_id": tenant_id or "global"
            })
            return False
    
    # Private helper methods
    
    def _build_cache_key(self, scope: str, tenant_id: str | None) -> str:
        """Build Redis cache key for default model."""
        if scope == "global" or tenant_id is None:
            return "models:default"
        return f"models:default:tenant:{tenant_id}"
    
    async def _get_from_cache(self, cache_key: str) -> dict[str, Any] | None:
        """Get default model from Redis cache."""
        try:
            from db.redis_cache.client import get_redis, redis_available
            
            if not redis_available():
                return None
            
            redis = get_redis()
            cached_data = redis.get(cache_key)
            
            if cached_data:
                import json
                return json.loads(cached_data)
            
            return None
            
        except Exception as e:
            logger.debug("dmr.cache_get_failed", extra={
                "error": str(e),
                "cache_key": cache_key
            })
            return None
    
    async def _set_cache(self, cache_key: str, data: dict[str, Any]) -> bool:
        """Set default model in Redis cache with TTL."""
        try:
            from db.redis_cache.client import get_redis, redis_available
            
            if not redis_available():
                return False
            
            import json
            redis = get_redis()
            redis.setex(cache_key, self.cache_ttl, json.dumps(data))
            
            return True
            
        except Exception as e:
            logger.debug("dmr.cache_set_failed", extra={
                "error": str(e),
                "cache_key": cache_key
            })
            return False
    
    async def _get_from_db(
        self,
        scope: str,
        tenant_id: str | None
    ) -> dict[str, Any] | None:
        """Get default model from PostgreSQL."""
        try:
            from db.postgres_control.repositories import model_instance_repo
            
            default = model_instance_repo.get_default(scope=scope, tenant_id=tenant_id)
            
            if default:
                payload = self._serialize_llm_config(default)
                payload.update({
                    "source": "db",
                    "cached": False
                })
                return payload
            
            return None
            
        except Exception as e:
            logger.error("dmr.db_query_failed", extra={
                "error": str(e),
                "scope": scope,
                "tenant_id": tenant_id or "global"
            })
            return None
    
    async def _record_cache_hit(self, tenant_id: str | None) -> None:
        """Record cache hit metric."""
        try:
            from src.metrics.prometheus import dmr_cache_hits
            dmr_cache_hits.labels(tenant_id=tenant_id or "global").inc()
        except Exception:
            logger.debug("dmr: failed to record cache hit metric", exc_info=True)
    
    async def _record_cache_miss(self, tenant_id: str | None) -> None:
        """Record cache miss metric."""
        try:
            from src.metrics.prometheus import dmr_cache_misses
            dmr_cache_misses.labels(tenant_id=tenant_id or "global").inc()
        except Exception:
            logger.debug("dmr: failed to record cache miss metric", exc_info=True)

    def _serialize_llm_config(self, config: LLMModelConfig) -> dict[str, Any]:
        """Convert LLMModelConfig into a cache-friendly payload."""
        return {
            "instance_id": config.instance_id,
            "instance_name": config.instance_name,
            "model_id": config.provider_model_id,
            "provider_model_id": config.provider_model_id,
            "provider_id": config.provider_id,
            "provider_name": config.provider_name,
            "base_url": config.base_url,
            "config_source": config.source,
        }


# Singleton accessor
_dmr_instance: DefaultModelResolver | None = None


def get_dmr() -> DefaultModelResolver:
    """
    Get the global DMR singleton instance.
    
    Returns:
        DefaultModelResolver instance (thread-safe singleton)
    """
    global _dmr_instance
    if _dmr_instance is None:
        _dmr_instance = DefaultModelResolver()
    return _dmr_instance


__all__ = ["DefaultModelResolver", "get_dmr"]
