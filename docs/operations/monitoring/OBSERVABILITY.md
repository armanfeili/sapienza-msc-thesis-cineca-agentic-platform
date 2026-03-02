# Observability Guide

This document describes the comprehensive observability solution for the Cineca Agentic Platform, including distributed tracing, metrics, dashboards, and alerting.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [OpenTelemetry Tracing](#opentelemetry-tracing)
- [Prometheus Metrics](#prometheus-metrics)
- [Grafana Dashboards](#grafana-dashboards)
- [Alerting](#alerting)
- [Service Level Objectives (SLOs)](#service-level-objectives-slos)
- [Configuration](#configuration)
- [Integration Guide](#integration-guide)
- [Troubleshooting](#troubleshooting)

## Overview

The platform implements a **three-pillar observability strategy**:

1. **Distributed Tracing** (OpenTelemetry) - Request flow across services
2. **Metrics** (Prometheus) - Performance and health indicators
3. **Dashboards & Alerts** (Grafana + AlertManager) - Visualization and incident response

### Key Features

- ✅ **OpenTelemetry** traces across API → orchestrator → tools → LLM
- ✅ **Prometheus** metrics for requests, agents, LLM calls, tools, and errors
- ✅ **Agent-specific** instrumentation (runs, phases, tokens, queue depth)
- ✅ **Alerting** rules for availability, latency, errors, and resource usage
- ✅ **SLO definitions** with error budgets and breach procedures
- ✅ **Production-ready** with graceful degradation if observability is unavailable

## Architecture

```
┌──────────────┐
│   FastAPI    │ ← HTTP requests
│  Application │
└──────┬───────┘
       │
       ├─────→ OpenTelemetry Tracer ────→ OTLP Exporter ────→ Jaeger/Tempo
       │
       ├─────→ Prometheus Metrics ───────→ /metrics endpoint ───→ Prometheus
       │
       └─────→ Application Logic
                   │
                   ├─ Orchestrator (traced + metered)
                   ├─ LLM Calls (traced + metered)
                   └─ Tool Invocations (traced + metered)
```

### Data Flow

1. **Request arrives** → Trace span started, request counter incremented
2. **Orchestrator runs** → Agent metrics recorded (run start, active runs)
3. **LLM called** → LLM span created, call metrics + token counters incremented
4. **Tool invoked** → Tool span created, invocation metrics recorded
5. **Response returned** → Span closed, duration histogram updated, active runs decremented

## OpenTelemetry Tracing

### Setup

Tracing is configured in `src/observability/tracing.py`:

```python
from src.observability.tracing import setup_tracing, get_tracer, shutdown_tracing

# In main.py
app = FastAPI()
setup_tracing(app)

# In your code
tracer = get_tracer(__name__)
with tracer.start_as_current_span("operation_name") as span:
    span.set_attribute("key", "value")
    # ... your code ...
```

### Configuration

Environment variables control tracing:

```bash
# Enable tracing (default: false)
OTEL_ENABLED=true

# Service identification
OTEL_SERVICE_NAME=cineca-agentic-platform
OTEL_SERVICE_VERSION=1.0.0
ENVIRONMENT=production  # or development, staging

# OTLP Exporter endpoint
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317  # gRPC (default)
# OR
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318  # HTTP

# Sampling (production uses ratio-based)
OTEL_TRACE_SAMPLE_RATIO=0.1  # 10% of traces (production)
# Development always samples (AlwaysOn)

# Optional: Console exporter for debugging
OTEL_ENABLE_CONSOLE_EXPORTER=true
```

### Automatic Instrumentation

The following libraries are automatically instrumented:

- **FastAPI** - HTTP requests/responses
- **Requests** - Outbound HTTP calls
- **Logging** - Log correlation with trace IDs

### Span Attributes

Standard semantic conventions are used:

```python
span.set_attribute("http.method", "POST")
span.set_attribute("http.url", "/api/v1/agents/run")
span.set_attribute("http.status_code", 200)
span.set_attribute("agent.type", "rag-agent")
span.set_attribute("llm.model", "gpt-4")
span.set_attribute("llm.provider", "openai")
span.set_attribute("llm.tokens.prompt", 100)
span.set_attribute("llm.tokens.completion", 50)
```

### Example: Tracing an Agent Run

```python
from src.observability.tracing import get_tracer

tracer = get_tracer("orchestrator")

with tracer.start_as_current_span("agent_run") as span:
    span.set_attribute("agent.type", "rag-agent")
    span.set_attribute("agent.run_id", run_id)
    
    with tracer.start_as_current_span("planning_phase") as phase_span:
        # ... planning logic ...
        phase_span.set_attribute("plan.steps", len(steps))
    
    with tracer.start_as_current_span("llm_call") as llm_span:
        llm_span.set_attribute("llm.model", "gpt-4")
        result = await call_llm(prompt)
        llm_span.set_attribute("llm.tokens.total", result.tokens)
    
    with tracer.start_as_current_span("tool_invocation") as tool_span:
        tool_span.set_attribute("tool.name", "database.query")
        output = await invoke_tool(tool_name, inputs)
```

### Viewing Traces

Access traces via your OTLP-compatible backend:

- **Jaeger UI**: http://localhost:16686
- **Grafana Tempo**: http://localhost:3000/explore (select Tempo datasource)

Search by:
- Trace ID
- Service name (`cineca-agentic-platform`)
- Operation name (`agent_run`, `llm_call`, etc.)
- Tags (`agent.type`, `http.status_code`, etc.)

## Prometheus Metrics

### Metrics Endpoint

Metrics are exposed at:

```
GET /metrics
```

Returns Prometheus-formatted metrics suitable for scraping.

### Base Metrics

Defined in `src/observability/metrics.py`:

#### HTTP Metrics

```prometheus
# Request counter
http_requests_total{method="POST", path="/api/v1/agents/run", status="200"}

# Request duration histogram (buckets: 0.01s to 10s)
http_request_duration_seconds_bucket{method="POST", path="/api/v1/agents/run", le="0.5"}
http_request_duration_seconds_count{method="POST", path="/api/v1/agents/run"}
http_request_duration_seconds_sum{method="POST", path="/api/v1/agents/run"}
```

#### Background Job Metrics

```prometheus
background_jobs_total{job_type="cleanup", status="success"}
background_job_duration_seconds_bucket{job_type="cleanup", le="10"}
```

#### Tool Invocation Metrics

```prometheus
tool_invocations_total{tool_name="database.query", status="success"}
tool_invocation_duration_seconds_bucket{tool_name="database.query", le="1"}
tool_invocation_queue_depth{tool_name="database.query"} 0
tool_cache_operations_total{tool_name="database.query", operation="hit"}
tool_idempotency_conflicts_total{tool_name="database.query"}
```

### Agent Metrics

Defined in `src/observability/agent_metrics.py`:

#### Agent Run Metrics

```prometheus
# Total agent runs
agent_runs_total{agent_type="rag-agent", status="success", tenant_id="tenant-1"}

# Agent run duration histogram (buckets: 0.5s to 10min)
agent_run_duration_seconds_bucket{agent_type="rag-agent", le="30"}
agent_run_duration_seconds_count{agent_type="rag-agent"}
agent_run_duration_seconds_sum{agent_type="rag-agent"}

# Active agent runs (gauge)
agent_active_runs{agent_type="rag-agent", tenant_id="tenant-1"} 3

# Phase duration (planning, execution, etc.)
agent_phase_duration_seconds_bucket{agent_type="rag-agent", phase="planning", le="5"}
```

#### LLM Metrics

```prometheus
# LLM call counter
llm_calls_total{model="gpt-4", provider="openai", status="success"}

# LLM call duration histogram (buckets: 0.1s to 60s)
llm_call_duration_seconds_bucket{model="gpt-4", provider="openai", le="10"}

# Token counters
llm_tokens_total{model="gpt-4", provider="openai", type="prompt"} 1500
llm_tokens_total{model="gpt-4", provider="openai", type="completion"} 800
llm_tokens_total{model="gpt-4", provider="openai", type="total"} 2300

# LLM errors
llm_errors_total{model="gpt-4", provider="openai", error_type="rate_limit"}
```

#### Agent Tool Call Metrics

```prometheus
# Tool calls within agent context
agent_tool_calls_total{agent_type="rag-agent", tool_name="database.query", status="success"}
```

#### Agent Error Metrics

```prometheus
# Errors by type and phase
agent_errors_total{agent_type="rag-agent", error_type="timeout", phase="execution"}
```

#### Agent Queue Metrics

```prometheus
# Queue depth by priority
agent_queue_depth{priority="high"} 5
```

#### Orchestrator Metrics

```prometheus
# Orchestrator steps
orchestrator_steps_total{agent_type="rag-agent", step_type="tool_selection"}
orchestrator_step_duration_seconds_bucket{agent_type="rag-agent", step_type="tool_selection", le="1"}
```

### Recording Metrics

Use helper functions to record metrics:

```python
from src.observability.agent_metrics import (
    record_agent_run_start,
    record_agent_run_complete,
    record_llm_call,
    record_agent_tool_call,
    record_agent_error,
    record_orchestrator_step,
)

# Start an agent run
record_agent_run_start("rag-agent", "tenant-1", app)

# Record LLM call
record_llm_call(
    model="gpt-4",
    provider="openai",
    status="success",
    duration_seconds=2.5,
    prompt_tokens=100,
    completion_tokens=50,
    app=app,
)

# Record tool call within agent
record_agent_tool_call(
    "rag-agent", "database.query", "success", 0.3, app
)

# Record agent error
record_agent_error("rag-agent", "timeout", "execution", app)

# Complete agent run
record_agent_run_complete(
    "rag-agent", "success", 15.5, "tenant-1", app
)
```

### Prometheus Configuration

Configure Prometheus to scrape the platform:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'cineca-agentic-platform'
    scrape_interval: 15s
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
```

## Grafana Dashboards

### Recommended Dashboards

Create the following dashboards in Grafana:

#### 1. SLO Overview Dashboard

**Panels**:
- API Availability (%) - 7-day rolling
- Error Budget Remaining (%) by SLO
- SLO Burn Rate (4-panel: 1h, 6h, 24h, 7d)
- Critical SLO Violations (table)

**Queries**:
```promql
# API Availability
(
  sum(rate(http_requests_total{status=~"2.."}[7d]))
  /
  sum(rate(http_requests_total[7d]))
) * 100

# Error Budget Remaining
(
  1 - (
    (1 - (sum(rate(http_requests_total{status=~"2.."}[7d])) / sum(rate(http_requests_total[7d]))))
    / (1 - 0.999)
  )
) * 100
```

#### 2. API Performance Dashboard

**Panels**:
- Request Rate (req/s) by endpoint
- Latency (p50, p95, p99) by endpoint
- Error Rate (%) by endpoint
- HTTP Status Codes (breakdown)

**Queries**:
```promql
# Request rate
sum(rate(http_requests_total[5m])) by (path)

# p95 latency
histogram_quantile(0.95, 
  sum(rate(http_request_duration_seconds_bucket[5m])) by (path, le)
)

# Error rate
sum(rate(http_requests_total{status=~"5.."}[5m])) by (path)
/
sum(rate(http_requests_total[5m])) by (path)
```

#### 3. Agent Operations Dashboard

**Panels**:
- Agent Run Success Rate (%)
- Agent Run Duration (p50, p95, p99)
- Active Agent Runs (gauge)
- Agent Errors by Type
- Queue Depth by Priority

**Queries**:
```promql
# Success rate
sum(rate(agent_runs_total{status="success"}[5m]))
/
sum(rate(agent_runs_total[5m]))

# p95 duration
histogram_quantile(0.95,
  sum(rate(agent_run_duration_seconds_bucket[5m])) by (agent_type, le)
)

# Active runs
sum(agent_active_runs) by (agent_type)
```

#### 4. LLM Performance Dashboard

**Panels**:
- LLM Call Success Rate (%) by model/provider
- LLM Call Latency (p50, p95, p99) by model
- Token Usage (prompt, completion, total) by model
- LLM Errors by Type
- Cost Estimate (based on token usage)

**Queries**:
```promql
# Success rate
sum(rate(llm_calls_total{status="success"}[5m])) by (model, provider)
/
sum(rate(llm_calls_total[5m])) by (model, provider)

# Token usage
sum(rate(llm_tokens_total[5m])) by (model, type)

# Error rate
sum(rate(llm_errors_total[5m])) by (model, error_type)
```

### Dashboard Import

Grafana dashboards are defined in `ops/grafana/dashboards/` (JSON format).

Import via:
1. Grafana UI → Dashboards → Import
2. Paste JSON or upload file
3. Select Prometheus datasource

## Alerting

### Alert Rules

Alert rules are defined in `ops/prometheus/alerts.yml`.

#### Availability Alerts

```yaml
- alert: ServiceDown
  expr: up{job="cineca-agentic-platform"} == 0
  for: 1m
  labels:
    severity: critical
  annotations:
    summary: "Service {{ $labels.job }} is down"
    description: "{{ $labels.instance }} has been unreachable for 1 minute."

- alert: HighErrorRate
  expr: |
    (
      sum(rate(http_requests_total{status=~"5.."}[5m]))
      /
      sum(rate(http_requests_total[5m]))
    ) > 0.05
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "High HTTP error rate"
    description: "Error rate is {{ $value | humanizePercentage }} (threshold: 5%)"
```

#### Latency Alerts

```yaml
- alert: HighAPILatency
  expr: |
    histogram_quantile(0.95,
      sum(rate(http_request_duration_seconds_bucket[5m])) by (le)
    ) > 2
  for: 10m
  labels:
    severity: warning
  annotations:
    summary: "API p95 latency above 2s"
    description: "p95 latency is {{ $value }}s"
```

#### Agent Alerts

```yaml
- alert: AgentFailureRate
  expr: |
    (
      sum(rate(agent_runs_total{status!="success"}[5m]))
      /
      sum(rate(agent_runs_total[5m]))
    ) > 0.01
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Agent failure rate above 1%"
    description: "Failure rate: {{ $value | humanizePercentage }}"
```

#### LLM Alerts

```yaml
- alert: LLMRateLimitErrors
  expr: sum(rate(llm_errors_total{error_type="rate_limit"}[5m])) > 1
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "LLM rate limiting detected"
    description: "{{ $value }} rate limit errors/s"
```

### AlertManager Configuration

Configure AlertManager (`ops/prometheus/alertmanager.yml`):

```yaml
route:
  receiver: 'team-notifications'
  group_by: ['severity']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h

receivers:
  - name: 'team-notifications'
    slack_configs:
      - api_url: 'https://hooks.slack.com/services/YOUR/WEBHOOK/URL'
        channel: '#alerts'
        title: 'Cineca Platform Alert'
        text: '{{ range .Alerts }}{{ .Annotations.summary }}\n{{ .Annotations.description }}\n{{ end }}'
```

## Service Level Objectives (SLOs)

See [SLO.md](./SLO.md) for comprehensive SLO definitions.

### Key SLOs

| SLO | Target | Measurement Window | Error Budget |
|-----|--------|-------------------|--------------|
| API Availability | 99.9% | 30 days | 43.2 min/month |
| API Latency (Critical) | p95 < 500ms | 24 hours | - |
| API Latency (Standard) | p95 < 2s | 24 hours | - |
| Agent Success Rate | 99% | 7 days | 1% |
| LLM Success Rate | 98% | 24 hours | 2% |

### SLO Monitoring

Grafana dashboards display:
- **SLO Attainment** - Current % vs target
- **Error Budget Remaining** - % of budget left
- **Burn Rate** - How fast error budget is depleting
- **Trend** - Historical SLO performance

## Configuration

### Environment Variables

```bash
# === OpenTelemetry Tracing ===
OTEL_ENABLED=true
OTEL_SERVICE_NAME=cineca-agentic-platform
OTEL_SERVICE_VERSION=1.0.0
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_TRACE_SAMPLE_RATIO=0.1
ENVIRONMENT=production

# === Prometheus Metrics ===
# No config needed - /metrics endpoint auto-created

# === Multi-process Metrics (if using Gunicorn) ===
PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc

# === Grafana ===
# Configure datasources in Grafana UI or provisioning
```

### Application Settings

In `src/core/config.py` or `.env`:

```python
class Settings(BaseSettings):
    # ... other settings ...
    
    # Observability
    otel_enabled: bool = False
    otel_service_name: str = "cineca-agentic-platform"
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    environment: str = "development"
```

## Integration Guide

### 1. Enable Tracing in main.py

```python
from src.observability.tracing import setup_tracing, shutdown_tracing

app = FastAPI()

# Setup tracing
setup_tracing(app)

# ... routes, middleware, etc. ...

@app.on_event("shutdown")
async def shutdown():
    shutdown_tracing()
```

### 2. Enable Metrics in main.py

```python
from src.observability.metrics import setup_metrics
from src.observability.agent_metrics import setup_agent_metrics

app = FastAPI()

# Setup metrics
setup_metrics(app)
setup_agent_metrics(app)

# Metrics available at GET /metrics
```

### 3. Instrument Agent Orchestrator

```python
# src/orchestrator/agent_runner.py
from src.observability.tracing import get_tracer
from src.observability.agent_metrics import (
    record_agent_run_start,
    record_agent_run_complete,
    record_agent_phase,
    record_llm_call,
    record_agent_tool_call,
    record_agent_error,
)

tracer = get_tracer("orchestrator")

async def run_agent(agent_type: str, inputs: dict, tenant_id: str):
    # Start metrics
    record_agent_run_start(agent_type, tenant_id, app)
    
    start_time = time.time()
    
    with tracer.start_as_current_span("agent_run") as span:
        span.set_attribute("agent.type", agent_type)
        span.set_attribute("tenant.id", tenant_id)
        
        try:
            # Planning phase
            with tracer.start_as_current_span("planning") as phase_span:
                plan_start = time.time()
                plan = await create_plan(inputs)
                plan_duration = time.time() - plan_start
                record_agent_phase(agent_type, "planning", plan_duration, app)
            
            # Execution phase
            with tracer.start_as_current_span("execution") as exec_span:
                exec_start = time.time()
                
                # LLM call
                llm_start = time.time()
                llm_result = await call_llm(plan.prompt)
                llm_duration = time.time() - llm_start
                record_llm_call(
                    "gpt-4", "openai", "success", llm_duration,
                    llm_result.prompt_tokens, llm_result.completion_tokens, app
                )
                
                # Tool invocation
                tool_start = time.time()
                tool_output = await invoke_tool("database.query", inputs)
                tool_duration = time.time() - tool_start
                record_agent_tool_call(
                    agent_type, "database.query", "success", tool_duration, app
                )
                
                exec_duration = time.time() - exec_start
                record_agent_phase(agent_type, "execution", exec_duration, app)
            
            # Success
            total_duration = time.time() - start_time
            record_agent_run_complete(
                agent_type, "success", total_duration, tenant_id, app
            )
            
            return result
            
        except Exception as e:
            # Record error
            record_agent_error(agent_type, type(e).__name__, "execution", app)
            
            # Complete with failure
            total_duration = time.time() - start_time
            record_agent_run_complete(
                agent_type, "error", total_duration, tenant_id, app
            )
            
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
            raise
```

### 4. Deploy Observability Stack

#### Docker Compose

```yaml
# docker-compose.observability.yml
version: '3.8'

services:
  # Jaeger (OpenTelemetry backend)
  jaeger:
    image: jaegertracing/all-in-one:latest
    ports:
      - "16686:16686"  # Jaeger UI
      - "4317:4317"    # OTLP gRPC
      - "4318:4318"    # OTLP HTTP
    environment:
      - COLLECTOR_OTLP_ENABLED=true

  # Prometheus
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./ops/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
      - ./ops/prometheus/alerts.yml:/etc/prometheus/alerts.yml
    ports:
      - "9090:9090"
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.enable-lifecycle'

  # AlertManager
  alertmanager:
    image: prom/alertmanager:latest
    volumes:
      - ./ops/prometheus/alertmanager.yml:/etc/alertmanager/alertmanager.yml
    ports:
      - "9093:9093"

  # Grafana
  grafana:
    image: grafana/grafana:latest
    volumes:
      - ./ops/grafana/datasources:/etc/grafana/provisioning/datasources
      - ./ops/grafana/dashboards:/etc/grafana/provisioning/dashboards
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_USERS_ALLOW_SIGN_UP=false
```

Start with:
```bash
docker-compose -f docker-compose.observability.yml up -d
```

## Troubleshooting

### Traces Not Appearing

**Check**:
1. `OTEL_ENABLED=true` in environment
2. OTLP exporter endpoint reachable
3. No errors in logs: `grep -i "otel\|trace" logs/app.log`
4. Sampling ratio not too low (use 1.0 in dev)

**Debug**:
```bash
# Enable console exporter
export OTEL_ENABLE_CONSOLE_EXPORTER=true

# Check logs for trace output
tail -f logs/app.log | grep SpanExporter
```

### Metrics Missing

**Check**:
1. `/metrics` endpoint accessible: `curl http://localhost:8000/metrics`
2. Prometheus scraping successfully: Check Prometheus UI → Targets
3. Metrics registered: Check for "already registered" errors in logs

**Debug**:
```bash
# Check if metrics endpoint returns data
curl http://localhost:8000/metrics | grep agent_runs_total

# Check Prometheus config
docker exec prometheus cat /etc/prometheus/prometheus.yml
```

### Alerts Not Firing

**Check**:
1. Alert rules loaded: Prometheus UI → Alerts
2. Alert evaluation interval (default: 1m)
3. AlertManager receiving alerts: AlertManager UI
4. Notification channel configured

**Debug**:
```promql
# Manually run alert query in Prometheus
(
  sum(rate(http_requests_total{status=~"5.."}[5m]))
  /
  sum(rate(http_requests_total[5m]))
) > 0.05
```

### High Cardinality Issues

**Problem**: Too many unique label combinations causing Prometheus performance issues.

**Solution**:
1. Avoid high-cardinality labels (user IDs, timestamps, etc.)
2. Use `tenant_id` sparingly (only where necessary)
3. Aggregate before storing (e.g., use buckets for agent types)

**Monitor**:
```promql
# Check cardinality
count(http_requests_total) by (__name__)
count(agent_runs_total) by (__name__)
```

### Performance Impact

**Tracing overhead**: ~1-5% CPU, minimal memory
**Metrics overhead**: ~0.5-2% CPU, ~10-50 MB memory

**Optimization**:
1. Lower trace sampling ratio in production (0.01 = 1%)
2. Use asynchronous exporters (default)
3. Batch spans before exporting (default: 512 spans or 5s)

## References

- [OpenTelemetry Python Documentation](https://opentelemetry.io/docs/instrumentation/python/)
- [Prometheus Best Practices](https://prometheus.io/docs/practices/naming/)
- [Grafana Dashboarding](https://grafana.com/docs/grafana/latest/dashboards/)
- [SRE Book - Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/)

## Next Steps

1. **Create Grafana dashboards** → Visual monitoring
2. **Configure AlertManager** → Incident notifications
3. **Add custom metrics** → Business-specific indicators
4. **Implement SLO tracking** → Reliability measurement
5. **Add trace sampling strategies** → Cost optimization
