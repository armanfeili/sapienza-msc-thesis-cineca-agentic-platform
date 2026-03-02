"""
Health check configuration from environment variables.

Provides centralized configuration for timeouts, thresholds, fallback flags,
and component requirements.
"""

import os
from dataclasses import dataclass

from src.config import settings


@dataclass
class HealthConfig:
    """Configuration for health check system."""

    # Timeouts (milliseconds)
    timeout_ms: int = 1000
    db_timeout_ms: int = 3000
    postgres_timeout_ms: int = 10000
    postgres_retries: int = 2
    postgres_retry_backoff_ms: int = 250
    cache_timeout_ms: int = 3000

    # Thresholds
    worker_queue_max: int = 50

    # Fallback flags (allow degraded vs error when component missing/unavailable)
    allow_degraded: bool = True
    allow_mg_health_fallback: bool = True
    allow_redis_health_fallback: bool = True

    # Required components for readiness (others are optional/informational)
    required_components: set[str] = None  # type: ignore

    # Migration enforcement
    enforce_migrations: bool = False

    # Rate limit validation (production mode required in prod environments)
    rate_limit_mode: str = "test"  # "test" | "prod"

    def __post_init__(self):
        """Initialize required components set."""
        if self.required_components is None:
            # Default required: app, postgres, redis
            # Memgraph is optional (policy-controlled)
            # Providers, workers are optional (degraded ok)
            # Observability (ollama, prometheus, grafana, ui) are informational only
            self.required_components = {"app", "postgres", "redis"}


def get_health_config() -> HealthConfig:
    """
    Build HealthConfig from environment variables.

    Environment variables:
    - HEALTH_TIMEOUT_MS: Global probe timeout (default 1000)
    - HEALTH_DB_TIMEOUT_MS: Database probe timeout (default 3000)
    - HEALTH_POSTGRES_TIMEOUT_MS: PostgreSQL probe timeout (default 10000)
    - HEALTH_POSTGRES_RETRIES: PostgreSQL probe max attempts (default 2)
    - HEALTH_POSTGRES_RETRY_BACKOFF_MS: Backoff between retries (default 250)
    - HEALTH_CACHE_TIMEOUT_MS: Cache probe timeout (default 3000)
    - READY_ALLOW_DEGRADED: Allow degraded components in ready state (default 1)
    - HEALTH_ALLOW_MG_HEALTH_FALLBACK: Allow Memgraph fallback (default 1)
    - HEALTH_ALLOW_REDIS_HEALTH_FALLBACK: Allow Redis fallback (default 1)
    - WORKER_QUEUE_MAX: Max queue depth threshold (default 50)
    - ENFORCE_MIGRATIONS: Require migrations for startup (default 0)
    - RATE_LIMIT_MODE: Rate limit mode ("test" | "prod", default from settings)
    """
    postgres_timeout_default = os.getenv("HEALTH_POSTGRES_TIMEOUT_MS", None)
    if postgres_timeout_default is None:
        postgres_timeout_default = os.getenv("HEALTH_DB_TIMEOUT_MS", "10000")
    return HealthConfig(
        timeout_ms=int(os.getenv("HEALTH_TIMEOUT_MS", "1000")),
        db_timeout_ms=int(os.getenv("HEALTH_DB_TIMEOUT_MS", "3000")),
        postgres_timeout_ms=int(postgres_timeout_default),
        postgres_retries=int(os.getenv("HEALTH_POSTGRES_RETRIES", "2")),
        postgres_retry_backoff_ms=int(os.getenv("HEALTH_POSTGRES_RETRY_BACKOFF_MS", "250")),
        cache_timeout_ms=int(os.getenv("HEALTH_CACHE_TIMEOUT_MS", "3000")),
        worker_queue_max=int(os.getenv("WORKER_QUEUE_MAX", "50")),
        allow_degraded=os.getenv("READY_ALLOW_DEGRADED", "1") not in ("0", "false", "False"),
        allow_mg_health_fallback=os.getenv("HEALTH_ALLOW_MG_HEALTH_FALLBACK", "1") not in ("0", "false", "False"),
        allow_redis_health_fallback=os.getenv("HEALTH_ALLOW_REDIS_HEALTH_FALLBACK", "1") not in ("0", "false", "False"),
        enforce_migrations=os.getenv("ENFORCE_MIGRATIONS", "0") not in ("0", "false", "False"),
        rate_limit_mode=os.getenv("RATE_LIMIT_MODE", getattr(settings, "RATE_LIMIT_MODE", "test")),
    )
