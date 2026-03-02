"""
Default Model Resolver Metrics

Prometheus instrumentation for default model resolution, caching, warmup,
and provider health operations.

Metrics:
- default_model_name: Current default model (gauge with labels)
- model_warmup_seconds: Model warmup duration histogram
- provider_health_status: Provider health gauge (1=healthy, 0=unhealthy)
- dmr_cache_hits: DMR cache hit counter
- dmr_cache_misses: DMR cache miss counter
"""

from prometheus_client import Counter, Gauge, Histogram

# ──────────────────────────────────────────────────────────────────
# Default Model Metrics
# ──────────────────────────────────────────────────────────────────

default_model_name = Gauge(
    "default_model_name",
    "Current default model name by scope and tenant",
    labelnames=["scope", "tenant_id", "model_name"],
)
"""
Gauge tracking current default model configuration.

Labels:
- scope: 'global', 'tenant', or 'user'
- tenant_id: Tenant identifier (or 'global' for global scope)
- model_name: Name of the default model

Value is always 1.0 when the model is active, 0.0 when removed.

Example:
    default_model_name.labels(scope="global", tenant_id="global", model_name="phi3:mini").set(1.0)
    default_model_name.labels(scope="tenant", tenant_id="acme-corp", model_name="gpt-4").set(1.0)
"""

# ──────────────────────────────────────────────────────────────────
# Model Warmup Metrics
# ──────────────────────────────────────────────────────────────────

model_warmup_seconds = Histogram(
    "model_warmup_seconds",
    "Duration of model warmup operations",
    labelnames=["model_name", "provider", "status"],
    buckets=(0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)
"""
Histogram tracking model warmup latency distribution.

Labels:
- model_name: Name of model being warmed up
- provider: Provider identifier (ollama, openai, azure, etc.)
- status: 'success', 'timeout', 'error'

Buckets optimized for warmup scenarios:
- 0.5s: Hot cache
- 1-5s: Warm start
- 10-30s: Cold start
- 60-300s: Heavy model loading

Example:
    model_warmup_seconds.labels(
        model_name="phi3:mini",
        provider="ollama",
        status="success"
    ).observe(12.5)
"""

# ──────────────────────────────────────────────────────────────────
# Provider Health Metrics
# ──────────────────────────────────────────────────────────────────

provider_health_status = Gauge(
    "provider_health_status",
    "Provider health status (1=healthy, 0=unhealthy)",
    labelnames=["provider", "model_name"],
)
"""
Gauge tracking provider health by provider and model.

Labels:
- provider: Provider identifier (ollama, openai, azure, etc.)
- model_name: Model being health-checked

Value:
- 1.0: Provider healthy and model available
- 0.0: Provider unhealthy or model unavailable

Example:
    provider_health_status.labels(provider="ollama", model_name="phi3:mini").set(1.0)
    provider_health_status.labels(provider="openai", model_name="gpt-4").set(0.0)
"""

# ──────────────────────────────────────────────────────────────────
# DMR Cache Metrics
# ──────────────────────────────────────────────────────────────────

dmr_cache_hits = Counter(
    "dmr_cache_hits_total",
    "Total DMR cache hits (Redis)",
    labelnames=["scope", "tenant_id"],
)
"""
Counter tracking successful DMR cache retrievals from Redis.

Labels:
- scope: 'global', 'tenant', or 'user'
- tenant_id: Tenant identifier (or 'global' for global scope)

Example:
    dmr_cache_hits.labels(scope="global", tenant_id="global").inc()
    dmr_cache_hits.labels(scope="tenant", tenant_id="acme-corp").inc()
"""

dmr_cache_misses = Counter(
    "dmr_cache_misses_total",
    "Total DMR cache misses (fell through to PostgreSQL)",
    labelnames=["scope", "tenant_id"],
)
"""
Counter tracking DMR cache misses requiring PostgreSQL lookup.

Labels:
- scope: 'global', 'tenant', or 'user'
- tenant_id: Tenant identifier (or 'global' for global scope)

High miss rate may indicate:
- Cache TTL too short
- Frequent default model changes
- Redis connectivity issues

Example:
    dmr_cache_misses.labels(scope="global", tenant_id="global").inc()
    dmr_cache_misses.labels(scope="tenant", tenant_id="acme-corp").inc()
"""

# ──────────────────────────────────────────────────────────────────
# Recording Functions
# ──────────────────────────────────────────────────────────────────


def set_default_model(scope: str, tenant_id: str, model_name: str) -> None:
    """
    Record current default model configuration.

    Sets gauge to 1.0 for the active model. Should be called whenever:
    - DMR resolves a default model successfully
    - PATCH /models/defaults updates the default
    - Cache is warmed up at startup

    Args:
        scope: Resolution scope ('global', 'tenant', 'user')
        tenant_id: Tenant ID or 'global' for global scope
        model_name: Name of the default model

    Example:
        set_default_model("global", "global", "phi3:mini")
        set_default_model("tenant", "acme-corp", "gpt-4")
    """
    default_model_name.labels(scope=scope, tenant_id=tenant_id, model_name=model_name).set(1.0)


def record_model_warmup(model_name: str, provider: str, status: str, duration_seconds: float) -> None:
    """
    Record model warmup operation duration.

    Should be called after every warmup attempt (success or failure).

    Args:
        model_name: Name of model warmed up
        provider: Provider identifier (ollama, openai, azure, etc.)
        status: Operation status ('success', 'timeout', 'error')
        duration_seconds: Warmup duration in seconds

    Example:
        record_model_warmup("phi3:mini", "ollama", "success", 12.5)
        record_model_warmup("gpt-4", "openai", "timeout", 300.0)
    """
    model_warmup_seconds.labels(model_name=model_name, provider=provider, status=status).observe(duration_seconds)


def set_provider_health(provider: str, model_name: str, healthy: bool) -> None:
    """
    Update provider health status.

    Should be called by provider health checker on each probe result.

    Args:
        provider: Provider identifier (ollama, openai, azure, etc.)
        model_name: Model being health-checked
        healthy: True if provider is healthy and model available

    Example:
        set_provider_health("ollama", "phi3:mini", True)
        set_provider_health("openai", "gpt-4", False)
    """
    provider_health_status.labels(provider=provider, model_name=model_name).set(1.0 if healthy else 0.0)


def record_dmr_cache_hit(scope: str, tenant_id: str) -> None:
    """
    Record DMR cache hit (successful Redis retrieval).

    Should be called by DMR when cache lookup succeeds.

    Args:
        scope: Resolution scope ('global', 'tenant', 'user')
        tenant_id: Tenant ID or 'global' for global scope

    Example:
        record_dmr_cache_hit("global", "global")
        record_dmr_cache_hit("tenant", "acme-corp")
    """
    dmr_cache_hits.labels(scope=scope, tenant_id=tenant_id).inc()


def record_dmr_cache_miss(scope: str, tenant_id: str) -> None:
    """
    Record DMR cache miss (fell through to PostgreSQL).

    Should be called by DMR when cache lookup fails and PostgreSQL is queried.

    Args:
        scope: Resolution scope ('global', 'tenant', 'user')
        tenant_id: Tenant ID or 'global' for global scope

    Example:
        record_dmr_cache_miss("global", "global")
        record_dmr_cache_miss("tenant", "acme-corp")
    """
    dmr_cache_misses.labels(scope=scope, tenant_id=tenant_id).inc()
