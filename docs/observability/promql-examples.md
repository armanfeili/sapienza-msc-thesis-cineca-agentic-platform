````markdown
# PromQL Examples

This document contains **Prometheus Query Language (PromQL)** examples used in our Grafana dashboards and alerting rules.  
They are organized by category for quick reference.

---

## 1. HTTP Request Metrics

### 1.1 Request Rate (RPS)
Number of requests per second over the last minute:
```promql
sum(rate(http_requests_total[1m]))
````

### 1.2 Request Rate per Endpoint

```promql
sum by (method, path) (rate(http_requests_total[1m]))
```

### 1.3 Error Rate (% of 4xx and 5xx)

```promql
(
  sum(rate(http_requests_total{status=~"4..|5.."}[5m]))
/
  sum(rate(http_requests_total[5m]))
) * 100
```

### 1.4 Request Latency (p95)

```promql
histogram_quantile(
  0.95,
  sum(rate(http_request_duration_seconds_bucket[5m])) by (le)
)
```

---

## 2. CPU, Memory, and Resource Usage

### 2.1 CPU Usage (%)

```promql
100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)
```

### 2.2 Memory Usage (%)

```promql
(node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes)
/
node_memory_MemTotal_bytes * 100
```

### 2.3 Disk Usage (%)

```promql
(node_filesystem_size_bytes{fstype!="tmpfs"} - node_filesystem_free_bytes{fstype!="tmpfs"})
/
node_filesystem_size_bytes{fstype!="tmpfs"} * 100
```

---

## 3. Application-Specific Metrics

### 3.1 MCP Requests Throughput

```promql
sum(rate(mcp_requests_total[1m]))
```

### 3.2 MCP Error Rate

```promql
sum(rate(mcp_requests_total{status="error"}[5m])) 
/ 
sum(rate(mcp_requests_total[5m])) * 100
```

### 3.3 Average MCP Query Execution Time

```promql
sum(rate(mcp_query_duration_seconds_sum[5m])) 
/ 
sum(rate(mcp_query_duration_seconds_count[5m]))
```

---

## 4. Database (Memgraph) Metrics

### 4.1 Memgraph Queries per Second

```promql
sum(rate(memgraph_queries_executed_total[1m]))
```

### 4.2 Memgraph Query Error Rate

```promql
sum(rate(memgraph_queries_failed_total[5m])) 
/ 
sum(rate(memgraph_queries_executed_total[5m])) * 100
```

### 4.3 Memgraph Memory Usage

```promql
memgraph_memory_usage_bytes
```

---

## 5. Alert-Oriented Queries

### 5.1 High CPU Alert

```promql
100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 85
```

### 5.2 High Error Rate Alert

```promql
(
  sum(rate(http_requests_total{status=~"5.."}[5m]))
/
  sum(rate(http_requests_total[5m]))
) * 100 > 5
```

### 5.3 Low Request Throughput Alert

```promql
sum(rate(http_requests_total[5m])) < 1
```

---

## 6. Network Metrics

### 6.1 Network Traffic (Bytes/s)

```promql
rate(node_network_transmit_bytes_total[1m]) 
+ rate(node_network_receive_bytes_total[1m])
```

### 6.2 Network Errors

```promql
rate(node_network_receive_errs_total[5m]) 
+ rate(node_network_transmit_errs_total[5m])
```

---

## 7. Example: SLO Burn Rate Calculation

### 7.1 Error Budget Burn Rate (1h Window)

```promql
(
  sum(rate(http_requests_total{status=~"5.."}[1h]))
/
  sum(rate(http_requests_total[1h]))
) / (1 - SLO_target)
```

Replace `SLO_target` with your defined target (e.g., `0.99` for 99% SLO).

---

## 8. Useful Prometheus Functions Reference

* `rate(metric[window])` – per-second average rate over the time window.
* `irate(metric[window])` – per-second instant rate (more spiky).
* `histogram_quantile(q, sum(rate(...)))` – quantile estimation for histograms.
* `avg`, `sum`, `min`, `max` – aggregation operators.
* `by (label)` – group results by label(s).
* `without (label)` – remove certain label(s) from grouping.

---

**Last updated:** 2025-08-09

