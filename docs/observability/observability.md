```markdown
# Observability Guide

## Overview

This document describes our **observability strategy**, encompassing **metrics**, **logs**, and **traces**, as well as alerting and dashboarding for both the application and infrastructure.  
The goal is to ensure we can **measure, monitor, and understand** the system’s state at any given time, and diagnose issues quickly.

Our observability stack is based on:
- **Prometheus** for metrics collection
- **Grafana** for visualization
- **OpenTelemetry (OTel)** for distributed tracing
- **Loki** for centralized log aggregation
- **Alertmanager** for automated alerts

---

## 1. Observability Principles

We follow these key principles:

1. **Instrument everything that matters**: business KPIs, application performance, infrastructure health.
2. **Standardize labels/tags** across metrics, logs, and traces for correlation.
3. **Correlate across signals**: metrics → logs → traces should allow drill-down.
4. **Alert on symptoms, not just causes**: focus alerts on user-facing impact.
5. **Make it self-service**: dashboards and queries should be accessible to developers and operators.

---

## 2. Observability Architecture

```

\[ Application Services ]
\|       &#x20;
\|        &#x20;
\[ OpenTelemetry SDK ]----\[ OTel Collector ]---\[ Prometheus ]---\[ Grafana ]
\|                             \               &#x20;
\|                              \                --> \[ Alertmanager ]
\|                              &#x20;
\|                                --> \[ Loki (Logs) ]

\--> \[ Tracing Backend (Jaeger/Tempo) ]

```

---

## 3. Metrics

### 3.1 Sources
- **Application-level**: via OpenTelemetry metrics SDK.
- **Infrastructure**: via Node Exporter, cAdvisor, and Kubernetes metrics.
- **Database**: via Memgraph's built-in metrics endpoint.

### 3.2 Metric Types
- **Counters**: monotonically increasing values (e.g., requests_total)
- **Gauges**: snapshot values (e.g., memory_usage_bytes)
- **Histograms**: distribution of values (e.g., request_duration_seconds)
- **Summaries**: precomputed percentiles (rarely used; prefer histograms)

### 3.3 Standard Labels
| Label        | Description                  |
|--------------|------------------------------|
| `service`    | Service name                  |
| `env`        | Environment (dev, staging, prod) |
| `instance`   | Host/container identifier     |
| `version`    | Application version           |
| `endpoint`   | API route or RPC method       |
| `status_code`| HTTP or gRPC status code      |

---

## 4. Logs

### 4.1 Logging Guidelines
- Use **structured logging** (JSON format).
- Include **trace IDs** and **span IDs** in logs for correlation.
- Use **log levels** consistently:
  - `DEBUG`: diagnostic information for developers
  - `INFO`: high-level application events
  - `WARN`: unexpected but non-fatal issues
  - `ERROR`: failures requiring investigation
  - `FATAL`: critical errors leading to termination

### 4.2 Centralized Logging
- Logs shipped to **Loki** via Promtail.
- Indexed by labels: `service`, `env`, `level`, `trace_id`.
- Retention: **30 days** (see Data Retention Policy).

---

## 5. Traces

### 5.1 Distributed Tracing Setup
- Instrumented with **OpenTelemetry SDK**.
- Exported via OTel Collector to **Jaeger** or **Tempo**.
- Trace context propagated across services using W3C Trace Context headers.

### 5.2 Trace Data
- Spans include:
  - `name`: operation name
  - `start_time` / `end_time`
  - `attributes`: HTTP method, URL, DB query, user ID
  - `status`: success/error

### 5.3 Sampling
- Default: **10% head-based sampling** in production to balance cost and coverage.
- Adjustable via environment variable `OTEL_TRACES_SAMPLING_RATE`.

---

## 6. Dashboards

We maintain Grafana dashboards for:
1. **Application Performance**: request rate, error rate, latency percentiles.
2. **Database Performance**: query execution time, connection pool usage.
3. **Infrastructure Health**: CPU, memory, disk, network I/O.
4. **Business Metrics**: active users, transaction volume.
5. **Custom Tool Metrics**: as defined in `docs/observability/mcp-tools-dashboard.json`.

---

## 7. Alerting

### 7.1 Alert Rules
- Defined in Prometheus alerting rules files.
- Examples:
  - **High Error Rate**: >5% HTTP 5xx responses in 5m
  - **High Latency**: 95th percentile latency > 2s for 5m
  - **Resource Saturation**: CPU > 90% for 10m

### 7.2 Alert Routing
- Alerts sent to Alertmanager, then routed to:
  - Slack channel `#alerts`
  - Email for critical incidents
  - PagerDuty for on-call escalation

---

## 8. Operational Runbooks

Each major alert has a corresponding runbook in `docs/runbooks/`:
- `incident-response.md` for triage and escalation.
- `backup-restore.md` for data recovery.
- `rotate-secrets.md` for compromised credentials.

---

## 9. Security and Compliance

- All monitoring data is subject to our **Privacy by Design** and **GDPR** policies.
- Sensitive user data is **never** stored in logs, traces, or metrics.
- Access to observability systems is restricted via RBAC.

---

**Last reviewed:** 2025-08-09
```
