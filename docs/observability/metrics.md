```markdown
# Metrics Guide

## Overview

This document defines the **metrics strategy** for the system, covering:
- **What** we measure
- **How** we measure it
- **Where** metrics are collected and stored
- **How** they are visualized and alerted upon

Our metrics follow the **RED** and **USE** principles:

- **RED** (for services):
  - **Rate**: requests per second
  - **Errors**: number of failed requests
  - **Duration**: latency of requests

- **USE** (for infrastructure):
  - **Utilization**: average time a resource is busy
  - **Saturation**: queued work waiting for the resource
  - **Errors**: count of errors in the resource

---

## 1. Metrics Architecture

```

\[ Application Services ]
|
\[ OpenTelemetry SDK / Prometheus Client ]
|
\[ OTel Collector / Prometheus Scrape ]
|
\[ Prometheus TSDB ] ----> \[ Grafana Dashboards ]
|
\[ Alertmanager ]

```

---

## 2. Metric Categories

We classify metrics into the following categories:

| Category         | Examples |
|------------------|----------|
| **Application**  | HTTP request counts, error rates, latencies |
| **Business**     | Active users, transactions processed, revenue |
| **Database**     | Query counts, query duration histograms, cache hit ratio |
| **Infrastructure** | CPU, memory, disk, network metrics |
| **Custom Tools** | Metrics for MCP tools and agent execution flow |

---

## 3. Metric Types

### 3.1 Counter
- Monotonically increasing value.
- Resets to 0 on restart.
- Example:
```

http\_requests\_total{service="api", method="GET", status\_code="200"} 152349

```

### 3.2 Gauge
- Represents a value that can go up or down.
- Example:
```

memory\_usage\_bytes{service="db"} 4.56e+08

```

### 3.3 Histogram
- Measures distributions (e.g., request durations).
- Example:
```

http\_request\_duration\_seconds\_bucket{le="0.1"} 320

````

### 3.4 Summary
- Similar to histograms but pre-computes quantiles.
- Less common; used for client-side metrics.

---

## 4. Standard Labels

| Label          | Description |
|----------------|-------------|
| `service`      | Name of the service emitting the metric |
| `env`          | Deployment environment (dev, staging, prod) |
| `version`      | Application version |
| `instance`     | Instance ID or hostname |
| `endpoint`     | API route, RPC method |
| `status_code`  | HTTP or gRPC status code |
| `db`           | Database name (if applicable) |
| `tool`         | MCP tool name (if applicable) |

---

## 5. Application Metrics

We instrument all services to expose Prometheus metrics at `/metrics`.

**Core application metrics:**
- `http_requests_total` (counter)
- `http_request_duration_seconds` (histogram)
- `http_request_errors_total` (counter)
- `active_sessions` (gauge)
- `background_job_duration_seconds` (histogram)
- `cache_hits_total` / `cache_misses_total` (counter)

---

## 6. Business Metrics

Business KPIs are also emitted as metrics:
- `active_users` (gauge)
- `transactions_total` (counter)
- `transaction_value_sum` (counter)
- `conversion_rate` (gauge)
- `recommendations_served_total` (counter)

---

## 7. Database Metrics

### Memgraph
- `mg_queries_total`
- `mg_query_duration_seconds`
- `mg_transactions_total`
- `mg_memory_usage_bytes`
- `mg_cache_hits_total` / `mg_cache_misses_total`

---

## 8. Infrastructure Metrics

Collected via Node Exporter and cAdvisor:
- `node_cpu_seconds_total` (per CPU mode)
- `node_memory_Active_bytes`
- `node_disk_io_time_seconds_total`
- `node_network_transmit_bytes_total`
- `node_network_receive_bytes_total`
- `container_cpu_usage_seconds_total`
- `container_memory_usage_bytes`

---

## 9. MCP Tool Metrics

We expose metrics for internal MCP tools and agents:
- `mcp_tool_invocations_total`
- `mcp_tool_duration_seconds`
- `mcp_tool_errors_total`
- `mcp_agent_steps_total`
- `mcp_agent_success_total`
- `mcp_agent_failure_total`

---

## 10. Dashboards

Metrics are visualized in Grafana dashboards:
1. **Application Performance** (RED metrics)
2. **Database Performance** (Memgraph dashboards)
3. **Infrastructure Health** (USE metrics)
4. **Custom MCP Tools Dashboard** (`mcp-tools-dashboard.json`)

---

## 11. Alerting Thresholds

Example Prometheus rules:
```yaml
groups:
- name: service-alerts
  rules:
    - alert: HighErrorRate
      expr: sum(rate(http_request_errors_total[5m])) / sum(rate(http_requests_total[5m])) > 0.05
      for: 5m
      labels:
        severity: critical
      annotations:
        summary: "High HTTP error rate"
        description: "More than 5% of HTTP requests failed in the last 5 minutes."

    - alert: HighLatency
      expr: histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le)) > 2
      for: 5m
      labels:
        severity: warning
      annotations:
        summary: "High request latency"
        description: "95th percentile latency is above 2 seconds."
````

---

## 12. Retention Policy

* **Application metrics**: 90 days
* **Business metrics**: 180 days
* **High-resolution metrics** (<1m scrape): downsampled after 30 days

---

**Last reviewed:** 2025-08-09

```
```
