# Observability Framework

The observability package provides comprehensive monitoring, metrics, tracing, and logging infrastructure for the Cineca Agentic Platform. It integrates Prometheus metrics, OpenTelemetry tracing, structured logging, and HTTP middleware to ensure full visibility into system behavior and performance.

## Architecture Overview

The observability framework is designed with the following principles:

- **Defensive Design**: All components gracefully degrade when dependencies are unavailable
- **Lazy Loading**: Components are imported and initialized only when needed
- **Configuration-Driven**: Behavior controlled via environment variables and settings
- **Multi-Tenant Aware**: Metrics and traces include tenant context where applicable
- **Performance Focused**: Minimal overhead when observability is disabled

## Core Components

### 1. Metrics (`metrics.py`)

Prometheus-based metrics collection with comprehensive instrumentation:

#### HTTP Metrics
- `http_requests_total`: Request counters by method, path, and status
- `http_request_duration_seconds`: Request latency histograms
- Service info gauge with version tracking

#### Background Job Metrics
- `background_jobs_total`: Job execution counters
- `background_job_duration_seconds`: Job duration histograms

#### Tool Metrics
- `tools_invocations_total`: Tool call counters with tenant context
- `tools_invocation_duration_seconds`: Tool execution latency
- `tools_queue_depth`: Current pending invocation queue size
- `tools_cache_operations_total`: Redis cache operation tracking
- `tools_idempotency_conflicts_total`: Idempotency violation counters

#### Intent Classification Metrics
- `intent_classification_total`: Classification event counters
- `intent_classification_duration_seconds`: Classification latency
- `intent_classification_confidence`: Confidence score distributions
- `intent_pattern_matches_total`: Pattern matching counters
- `intent_llm_fallback_total`: LLM fallback usage tracking
- `intent_rbac_adjustments_total`: RBAC-based intent adjustments

### 2. Agent Metrics (`agent_metrics.py`)

Specialized metrics for agent orchestration and execution:

#### Agent Run Metrics
- `agent_runs_total`: Agent execution counters by type, status, and tenant
- `agent_run_duration_seconds`: End-to-end agent run latency
- `agent_active_runs`: Currently executing agent gauge

#### Phase Metrics
- `agent_phase_duration_seconds`: Individual phase timing (planning, execution, etc.)

#### LLM Integration Metrics
- `llm_calls_total`: API call counters by model and provider
- `llm_call_duration_seconds`: LLM API latency
- `llm_tokens_total`: Token consumption tracking (prompt/completion/total)
- `llm_errors_total`: API error categorization

#### Tool Invocation Metrics
- `agent_tool_calls_total`: Tool calls within agent context
- `agent_tool_call_duration_seconds`: Tool execution latency

#### Error and Reliability Metrics
- `agent_errors_total`: Execution errors by type and phase
- `agent_retries_total`: Retry attempt tracking

#### Orchestration Metrics
- `orchestrator_steps_total`: Step execution counters
- `orchestrator_step_duration_seconds`: Step timing
- `agent_queue_depth`: Agent execution queue monitoring
- `agent_concurrency_limit`: Per-tenant concurrency limits
- `agent_concurrency_throttled_total`: Throttling event counters

### 3. Rate Limit Metrics (`rate_limit_metrics.py`)

Rate limiting and quota enforcement metrics:

- `rate_limit_requests_total`: Rate limit check counters
- `rate_limit_exceeded_total`: Rate limit violation tracking
- `tenant_quota_exceeded_total`: Tenant quota breach monitoring
- `rate_limit_usage_ratio`: Usage ratio histograms (current/limit)

### 4. Tracing (`tracing.py`)

OpenTelemetry-based distributed tracing with automatic instrumentation:

#### Features
- OTLP export over gRPC (4317) or HTTP/protobuf (4318)
- Configurable sampling (ratio-based in production, always-on in development)
- FastAPI, HTTP requests, and logging instrumentation
- Resource attributes (service name, version, environment, hostname)
- Graceful degradation when OTel libraries unavailable

#### Configuration
```python
# Environment variables
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_PROTOCOL=grpc
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
OTEL_SAMPLER_RATIO=0.2  # Production sampling
OTEL_CONSOLE_EXPORTER=false  # Debug console output
```

### 5. HTTP Middleware (`middleware.py`)

Request-level observability middleware providing:

- **Correlation IDs**: X-Request-ID header generation/propagation
- **Timing**: X-Process-Time response header
- **Metrics Recording**: Automatic Prometheus metric collection
- **Trace Context**: X-Trace-Id header when tracing active
- **Structured Logging**: Request context binding for consistent logs
- **Error Handling**: 5xx status recording even on exceptions

### 6. Package Bootstrap (`__init__.py`)

Unified configuration entry point for all observability components:

```python
from src.observability import configure as configure_observability

app = FastAPI()
results = configure_observability(
    app,
    enable_metrics=True,
    enable_tracing=True,
    enable_middleware=True
)
# Returns: {"metrics": bool, "tracing": bool, "middleware": bool}
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PROMETHEUS_MULTIPROC_DIR` | - | Enables multiprocess metrics collection |
| `OTEL_ENABLED` | `false` | Enable OpenTelemetry tracing |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `grpc` | OTLP protocol (grpc/http) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://otel-collector:4317` | OTLP collector endpoint |
| `OTEL_SAMPLER_RATIO` | `1.0` | Trace sampling ratio (0.0-1.0) |
| `OTEL_CONSOLE_EXPORTER` | `false` | Enable console trace output |

### FastAPI Integration

```python
from fastapi import FastAPI
from src.observability import configure as configure_observability

app = FastAPI(title="Cineca Agentic Platform")

# Configure all observability components
configure_observability(app)

# Metrics available at /metrics endpoint
# Tracing active if OTEL_ENABLED=true
```

## Usage Examples

### Recording Custom Metrics

```python
from src.observability.metrics import record_background_job

# Record background job execution
record_background_job(
    job_name="data_sync",
    status="success",
    duration_seconds=45.2
)
```

### Agent Metrics Recording

```python
from src.observability.agent_metrics import (
    record_agent_run_start,
    record_agent_run_complete,
    record_llm_call
)

# Track agent execution
record_agent_run_start("chat_agent", "tenant_123")

# Record LLM interaction
record_llm_call(
    model="gpt-4",
    provider="openai",
    status="success",
    duration_seconds=2.1,
    prompt_tokens=150,
    completion_tokens=75
)

record_agent_run_complete(
    agent_type="chat_agent",
    status="success",
    duration_seconds=5.8,
    tenant_id="tenant_123"
)
```

### Tracing Custom Operations

```python
from src.observability.tracing import get_tracer

tracer = get_tracer(__name__)

with tracer.start_as_current_span("custom_operation") as span:
    span.set_attribute("operation.param", value)
    # Your operation logic
    result = do_something()
    span.set_attribute("operation.result", result)
```

### Rate Limit Monitoring

```python
from src.observability.rate_limit_metrics import record_rate_limit_check

# Record rate limit decision
record_rate_limit_check(
    action="api_call",
    scope="user",
    allowed=True,
    current=45,
    limit=100
)
```

## Dependencies

### Required
- `prometheus-client`: Metrics collection and exposition
- `structlog`: Structured logging integration

### Optional
- `opentelemetry-distro`: Distributed tracing
- `opentelemetry-instrumentation-fastapi`: FastAPI auto-instrumentation
- `opentelemetry-instrumentation-requests`: HTTP client tracing
- `opentelemetry-instrumentation-logging`: Log correlation
- `opentelemetry-exporter-otlp-proto-grpc`: OTLP gRPC export
- `opentelemetry-exporter-otlp-proto-http`: OTLP HTTP export

## Security Considerations

- Metrics endpoints should be protected in production environments
- Trace data may contain sensitive information; ensure collector security
- Rate limiting metrics help detect abuse patterns
- Correlation IDs enable request tracking without exposing internal state

## Performance Impact

- **Metrics**: Minimal overhead (~1-5μs per metric recording)
- **Tracing**: Configurable sampling reduces production overhead
- **Middleware**: Request timing adds ~10-50μs per request
- **Logging**: Structured context binding has negligible impact

## Monitoring and Alerting

### Key Metrics for Alerting
- `agent_errors_total{phase="execution"} > 5` - Agent execution failures
- `llm_errors_total > 10` - LLM API failures
- `rate_limit_exceeded_total > 100` - Rate limit abuse
- `http_request_duration_seconds{quantile="0.95"} > 5.0` - Slow requests

### SLO Recommendations
- Agent success rate: >99%
- P95 request latency: <2 seconds
- LLM call success rate: >99.5%
- Tool execution success rate: >98%

## Troubleshooting

### Common Issues

1. **Metrics not appearing**: Check Prometheus registry initialization order
2. **Traces not exporting**: Verify OTLP endpoint connectivity and protocol
3. **High cardinality**: Use parameterized route templates, avoid dynamic labels
4. **Performance degradation**: Review sampling ratios and instrumentation scope

### Debug Mode

Enable console tracing for local development:
```bash
export OTEL_CONSOLE_EXPORTER=true
export OTEL_ENABLED=true
```

### Health Checks

Observability health can be verified via:
- `/metrics` endpoint returns Prometheus format data
- Structured logs contain `request_id` and `trace_id` fields
- Trace spans appear in configured collector</content>
<parameter name="filePath">/Users/armanfeili/Arman/Sapienza Courses/4-semester/Thesis/ILP-Thesis-2025/Cineca-Agentic-Platform/docs/general/README_observability.md