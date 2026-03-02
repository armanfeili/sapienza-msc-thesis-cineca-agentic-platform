# Health Framework Reference

This document provides comprehensive reference documentation for the Health framework implemented in the Cineca Agentic Platform. The Health framework provides a unified component-based health check system with standardized probes, policy-based readiness evaluation, and comprehensive monitoring.

## Overview

The Health framework is a comprehensive health check infrastructure designed for microservices and distributed systems. It provides:

- **Component Registry**: Centralized registry of all system components with health probes
- **Standardized Probes**: Consistent health check interface across all components
- **Policy-Based Evaluation**: Configurable readiness and startup policies
- **Multi-Level Checks**: Readiness, liveness, and startup health evaluations
- **Comprehensive Monitoring**: Detailed latency tracking and error reporting
- **Graceful Degradation**: Configurable fallback policies for component failures

## Architecture

### Core Components

The Health framework consists of several key components:

- **Component Registry** (`components.py`): Registry of all system components with probe functions
- **Health Configuration** (`config.py`): Environment-driven configuration for timeouts and policies
- **Health Policies** (`policy.py`): Evaluation logic for readiness and startup states
- **Health Endpoints**: FastAPI routers that expose health check endpoints

### Component Types

The framework supports multiple categories of components:

#### Core Components (Required for Readiness)
- **App**: Process liveness check
- **PostgreSQL**: Database connectivity and health
- **Redis**: Cache connectivity and queue health

#### Optional Components (Degraded OK)
- **Memgraph**: Graph database connectivity
- **Providers**: LLM provider registry health
- **Workers**: Background job queue health

#### Informational Components (Don't Affect Readiness)
- **Ollama**: Local LLM service availability
- **Prometheus**: Metrics collection service
- **Grafana**: Dashboard service

## Component Registry

### ComponentCheck Dataclass

The result of a component health probe:

```python
@dataclass
class ComponentCheck:
    ok: bool                    # Overall health status
    status: ComponentStatus     # Standardized status enum
    latency_ms: int | None      # Response time in milliseconds
    details: dict[str, Any]     # Component-specific details
```

### ComponentStatus Enum

Standardized health status values:

```python
class ComponentStatus(str, Enum):
    OK = "ok"           # Healthy and functional
    DEGRADED = "degraded"  # Functional with warnings/issues
    ERROR = "error"     # Not functional
    UNKNOWN = "unknown" # Not configured/unreachable
```

### Component Registry Class

Manages all system components and their probes:

```python
class ComponentRegistry:
    def __init__(self):
        self._components: dict[str, Callable[[], Coroutine[Any, Any, ComponentCheck]]] = {
            "app": probe_app,
            "postgres": probe_postgres,
            "redis": probe_redis,
            "memgraph": probe_memgraph,
            "providers": probe_providers,
            "workers": probe_workers,
            "ollama": probe_ollama,
            "prometheus": probe_prometheus,
            "grafana": probe_grafana,
        }
```

## Health Probes

### Core Probe Functions

#### probe_app()
**Purpose**: Process liveness check
**Type**: Liveness
**Implementation**: Simple boolean check (always OK if code executes)
**Response**:
```json
{
  "ok": true,
  "status": "ok",
  "latency_ms": 0,
  "details": {"process": "running"}
}
```

#### probe_postgres()
**Purpose**: PostgreSQL database connectivity
**Type**: Readiness (Required)
**Checks**:
- Connection establishment
- Simple SELECT 1 query execution
- Connection pool statistics
**Features**:
- Retry logic with configurable attempts and backoff
- Timeout protection
- Connection pool monitoring
**Response**:
```json
{
  "ok": true,
  "status": "ok",
  "latency_ms": 45,
  "details": {
    "database": "postgresql",
    "attempts": 1
  }
}
```

#### probe_redis()
**Purpose**: Redis connectivity and queue health
**Type**: Readiness (Required)
**Checks**:
- PING command execution
- Job queue depth statistics
- Connection health
**Features**:
- Consecutive failure tracking
- Degraded state for intermittent issues
- Queue depth monitoring
- Fallback policy support
**Response**:
```json
{
  "ok": true,
  "status": "ok",
  "latency_ms": 12,
  "details": {
    "queues": {
      "demo": 0,
      "test": 2,
      "long-running": 15
    }
  }
}
```

#### probe_memgraph()
**Purpose**: Memgraph graph database connectivity
**Type**: Optional (Informational)
**Checks**:
- Connection establishment
- Simple RETURN 1 query execution
**Features**:
- Informational-only (doesn't fail readiness)
- Generous timeouts for thread pool contention
- Graceful degradation
**Response**:
```json
{
  "ok": true,
  "status": "ok",
  "latency_ms": 234,
  "details": {"host": "memgraph:7687"}
}
```

#### probe_providers()
**Purpose**: LLM provider registry health
**Type**: Optional
**Checks**:
- PostgreSQL provider table accessibility
- Provider health status aggregation
- Individual provider connectivity
**Features**:
- Provider statistics aggregation
- Individual provider health details
- Tenant-scoped provider filtering
**Response**:
```json
{
  "ok": true,
  "status": "ok",
  "latency_ms": 67,
  "details": {
    "total": 5,
    "healthy": 4,
    "unhealthy": 1,
    "by_type": {"openai": 3, "ollama": 2},
    "providers": [
      {
        "name": "gpt-4o-mini",
        "type": "openai",
        "status": "healthy",
        "model": "gpt-4o-mini",
        "last_check": 1703123456
      }
    ]
  }
}
```

#### probe_workers()
**Purpose**: Background job queue health
**Type**: Optional
**Checks**:
- Redis queue depth monitoring
- Job backlog assessment
**Features**:
- Configurable queue max threshold
- Degraded state for high backlog
- Per-queue depth tracking
**Response**:
```json
{
  "ok": true,
  "status": "degraded",
  "latency_ms": 23,
  "details": {
    "queue_depth": 75,
    "queues": {
      "demo": 10,
      "test": 25,
      "long-running": 40
    }
  }
}
```

#### probe_ollama()
**Purpose**: Ollama service availability
**Type**: Informational
**Checks**:
- HTTP connectivity to Ollama API
- Model listing endpoint (/api/tags)
**Features**:
- Informational-only (doesn't affect readiness)
- Model count reporting
- Graceful failure handling
**Response**:
```json
{
  "ok": true,
  "status": "ok",
  "latency_ms": 89,
  "details": {
    "url": "http://ollama:11434",
    "models": 5
  }
}
```

#### probe_prometheus()
**Purpose**: Prometheus metrics service
**Type**: Informational
**Checks**:
- HTTP health endpoint (/health)
- Service availability
**Features**:
- Informational-only
- Database connectivity reporting
**Response**:
```json
{
  "ok": true,
  "status": "ok",
  "latency_ms": 12,
  "details": {
    "url": "http://prometheus:9090",
    "database": "available"
  }
}
```

#### probe_grafana()
**Purpose**: Grafana dashboard service
**Type**: Informational
**Checks**:
- HTTP health endpoint (/api/health)
- Database connectivity
**Features**:
- Informational-only
- Database status reporting
**Response**:
```json
{
  "ok": true,
  "status": "ok",
  "latency_ms": 34,
  "details": {
    "url": "http://grafana:3000",
    "database": "ok"
  }
}
```

## Health Configuration

### HealthConfig Class

Centralized configuration for health check behavior:

```python
@dataclass
class HealthConfig:
    # Timeouts (milliseconds)
    timeout_ms: int = 1000
    db_timeout_ms: int = 3000
    postgres_timeout_ms: int = 10000
    postgres_retries: int = 2
    postgres_retry_backoff_ms: int = 250
    cache_timeout_ms: int = 3000

    # Thresholds
    worker_queue_max: int = 50

    # Fallback flags
    allow_degraded: bool = True
    allow_mg_health_fallback: bool = True
    allow_redis_health_fallback: bool = True

    # Required components
    required_components: set[str] = None
```

### Environment Variables

```bash
# Timeouts
HEALTH_TIMEOUT_MS=1000
HEALTH_DB_TIMEOUT_MS=3000
HEALTH_POSTGRES_TIMEOUT_MS=10000
HEALTH_POSTGRES_RETRIES=2
HEALTH_POSTGRES_RETRY_BACKOFF_MS=250
HEALTH_CACHE_TIMEOUT_MS=3000

# Thresholds
WORKER_QUEUE_MAX=50

# Fallback policies
READY_ALLOW_DEGRADED=1
HEALTH_ALLOW_MG_HEALTH_FALLBACK=1
HEALTH_ALLOW_REDIS_HEALTH_FALLBACK=1

# Migration requirements
ENFORCE_MIGRATIONS=0
RATE_LIMIT_MODE=test
```

## Health Policies

### Readiness Evaluation

Determines if the service is ready to accept traffic:

```python
def evaluate_readiness(checks: dict[str, ComponentCheck]) -> tuple[str, int]:
    """
    Returns (status, http_code) where:
    - status: "ok", "degraded", "error"
    - http_code: 200 for ok/degraded, 503 for error
    """
```

**Readiness Policy**:
1. **Required Components**: Must be OK or degraded (with fallback)
2. **Optional Components**: Can be degraded without failing readiness
3. **Informational Components**: Don't affect readiness
4. **Degraded Tolerance**: Configurable via `allow_degraded`

### Startup Evaluation

Stricter evaluation for initial service startup:

```python
def evaluate_startup(checks: dict[str, ComponentCheck]) -> tuple[str, int, dict[str, Any]]:
    """
    Returns (status, http_code, extras) with additional startup checks
    """
```

**Startup Policy**:
- All readiness requirements must pass
- Migration enforcement (if `ENFORCE_MIGRATIONS=1`)
- Rate limit mode validation
- Environment diagnostics inclusion

## Health Endpoints

### /health/ready (Readiness)

Kubernetes readiness probe endpoint:

- **Method**: GET
- **Purpose**: Determines if service should receive traffic
- **Response Codes**: 200 (ready), 503 (not ready)
- **Content**: Component health status

**Response Format**:
```json
{
  "service": "cineca-agentic-platform",
  "version": "0.1.0",
  "status": "ok",
  "time": "2025-01-01T12:00:00Z",
  "checks": {
    "app": {"ok": true, "status": "ok", "latency_ms": 0},
    "postgres": {"ok": true, "status": "ok", "latency_ms": 45},
    "redis": {"ok": true, "status": "ok", "latency_ms": 12}
  }
}
```

### /health/live (Liveness)

Kubernetes liveness probe endpoint:

- **Method**: GET
- **Purpose**: Determines if service should be restarted
- **Response Codes**: 200 (alive), 503 (dead)
- **Content**: Basic process health

### /health/startup (Startup)

Kubernetes startup probe endpoint:

- **Method**: GET
- **Purpose**: Determines if service has finished starting
- **Response Codes**: 200 (started), 503 (starting)
- **Content**: Startup readiness with diagnostics

**Response Format**:
```json
{
  "service": "cineca-agentic-platform",
  "version": "0.1.0",
  "status": "ok",
  "time": "2025-01-01T12:00:00Z",
  "checks": {...},
  "environment": {
    "rate_limit_mode": "test",
    "rate_limit_backend": "redis"
  },
  "limits": {
    "llm": {"rpm": 60, "tpm": 40000}
  },
  "migrations": {
    "required": false,
    "applied": null
  }
}
```

## Monitoring and Metrics

### Prometheus Metrics

The health system integrates with Prometheus for comprehensive monitoring:

#### Health Check Metrics
```python
# Component health status
health_component_status{component="postgres", status="ok"} 1

# Health check latency
health_component_latency_seconds{component="postgres"} 0.045

# Health check counts
health_checks_total{component="postgres", status="ok"} 150
```

#### Consecutive Failure Tracking
```python
# Redis consecutive failures
redis_consecutive_failures 0

# Component degradation tracking
health_component_degraded{component="redis"} 0
```

### Structured Logging

All health checks emit structured logs:

```json
{
  "event": "health.postgres.ok",
  "component": "postgres",
  "latency_ms": 45,
  "attempts": 1
}
```

```json
{
  "event": "health.redis.timeout",
  "component": "redis",
  "timeout_ms": 2000,
  "consecutive": 2
}
```

## Error Handling and Resilience

### Timeout Management

All probes implement configurable timeouts:

- **Global Timeout**: `HEALTH_TIMEOUT_MS` (default: 1000ms)
- **Database Timeout**: `HEALTH_DB_TIMEOUT_MS` (default: 3000ms)
- **Cache Timeout**: `HEALTH_CACHE_TIMEOUT_MS` (default: 3000ms)

### Retry Logic

PostgreSQL probe includes retry logic:

- **Max Attempts**: `HEALTH_POSTGRES_RETRIES` (default: 2)
- **Backoff Delay**: `HEALTH_POSTGRES_RETRY_BACKOFF_MS` (default: 250ms)
- **Exponential Backoff**: Progressive delay between attempts

### Graceful Degradation

Components can degrade gracefully:

- **Redis Fallback**: Allow degraded state when Redis is unavailable
- **Memgraph Fallback**: Informational-only health checks
- **Provider Degradation**: Continue with unhealthy providers

### Failure Recovery

- **Consecutive Failure Tracking**: Monitor component reliability
- **Recovery Logging**: Log when components recover from failures
- **State Transitions**: Track component status changes

## Integration Examples

### FastAPI Router Integration

```python
from fastapi import APIRouter, HTTPException
from src.health.policy import evaluate_readiness, get_all_checks
from src.health.components import ComponentStatus

router = APIRouter()

@router.get("/health/ready")
async def readiness_probe():
    """Kubernetes readiness probe."""
    checks = await get_all_checks()
    status, http_code = evaluate_readiness(checks)
    
    if http_code != 200:
        raise HTTPException(status_code=http_code, detail=status)
    
    return {
        "status": status,
        "checks": {name: check.to_dict() for name, check in checks.items()}
    }
```

### Custom Health Checks

```python
from src.health.components import ComponentCheck, ComponentStatus, get_component_registry

# Add custom component
registry = get_component_registry()
registry._components["custom"] = probe_custom_service

async def probe_custom_service() -> ComponentCheck:
    """Custom health probe implementation."""
    try:
        # Custom health logic
        is_healthy = await check_custom_service()
        return ComponentCheck(
            ok=is_healthy,
            status=ComponentStatus.OK if is_healthy else ComponentStatus.ERROR,
            latency_ms=150,
            details={"service": "custom"}
        )
    except Exception as e:
        return ComponentCheck(
            ok=False,
            status=ComponentStatus.ERROR,
            details={"error": str(e)}
        )
```

### Configuration Override

```python
from src.health.config import HealthConfig

# Custom configuration
config = HealthConfig(
    timeout_ms=2000,
    db_timeout_ms=5000,
    allow_degraded=False,
    required_components={"app", "postgres", "redis", "custom"}
)
```

## Performance Considerations

### Probe Parallelization

All component probes run in parallel using `asyncio.gather()` for optimal performance.

### Connection Pooling

Database probes reuse existing connection pools to avoid connection overhead.

### Caching Strategies

- **Memgraph Connection Caching**: Reuse connections across health checks
- **Provider Health Caching**: Cache provider health status in Redis
- **Configuration Caching**: Cache parsed configuration values

### Resource Limits

- **Timeout Protection**: All probes have configurable timeouts
- **Concurrency Limits**: Parallel probe execution is bounded
- **Memory Bounds**: Response sizes are controlled

## Security Considerations

### Information Disclosure

Health endpoints avoid exposing sensitive information:

- **Credential Masking**: Database URLs with credentials are sanitized
- **Error Sanitization**: Stack traces are not exposed in responses
- **Access Control**: Health endpoints may require authentication

### Rate Limiting

Health endpoints should be rate-limited to prevent abuse:

- **Probe Frequency**: Limit health check frequency
- **Concurrent Requests**: Limit concurrent health checks
- **Response Caching**: Cache health responses briefly

## Troubleshooting

### Common Issues

#### PostgreSQL Connection Failures
- **Symptoms**: `postgres` component shows `ERROR` status
- **Causes**: Database down, network issues, authentication failures
- **Solutions**: Check database connectivity, verify credentials, check network

#### Redis Timeout Issues
- **Symptoms**: `redis` component shows `DEGRADED` or `ERROR`
- **Causes**: High latency, network issues, Redis overload
- **Solutions**: Check Redis connectivity, monitor queue depths, scale Redis

#### Provider Health Issues
- **Symptoms**: `providers` component shows `DEGRADED`
- **Causes**: LLM provider API issues, network problems
- **Solutions**: Check provider API status, verify API keys, monitor rate limits

### Debugging Tools

#### Health Check Logs
```bash
# View health check logs
tail -f logs/health.log | jq '.event | select(startswith("health."))'
```

#### Component Status Monitoring
```bash
# Monitor component status changes
kubectl logs -f deployment/cineca-agentic-platform | grep "health\."
```

#### Prometheus Queries
```promql
# Health check success rate
rate(health_checks_total{status="ok"}[5m]) / rate(health_checks_total[5m])

# Component latency percentiles
histogram_quantile(0.95, rate(health_component_latency_seconds_bucket[5m]))
```

This comprehensive Health framework provides robust service monitoring with configurable policies, comprehensive error handling, and excellent observability for production deployments.</content>
<parameter name="filePath">/Users/armanfeili/Arman/Sapienza Courses/4-semester/Thesis/ILP-Thesis-2025/Cineca-Agentic-Platform/docs/general/README_health.md