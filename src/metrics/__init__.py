"""
Metrics package for Prometheus instrumentation.

Provides domain-specific metrics for:
- Default Model Resolver (DMR)
- Model warmup operations
- Provider health checks
"""

from src.metrics.prometheus import (
    default_model_name,
    dmr_cache_hits,
    dmr_cache_misses,
    model_warmup_seconds,
    provider_health_status,
    record_dmr_cache_hit,
    record_dmr_cache_miss,
    record_model_warmup,
    set_default_model,
    set_provider_health,
)

__all__ = [
    # Metrics
    "default_model_name",
    "model_warmup_seconds",
    "provider_health_status",
    "dmr_cache_hits",
    "dmr_cache_misses",
    # Recording functions
    "record_dmr_cache_hit",
    "record_dmr_cache_miss",
    "record_model_warmup",
    "set_default_model",
    "set_provider_health",
]
