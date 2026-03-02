````markdown
# Dashboards Guide

## Overview

This document provides guidelines for creating, organizing, and maintaining **Grafana dashboards** for the platform’s observability stack.  
The goal is to make critical metrics **visible, actionable, and easy to navigate** for engineers, SREs, and stakeholders.

---

## 1. Principles for Dashboard Design

1. **Clarity First** – Prioritize legibility over visual complexity.
2. **Purpose-Driven** – Every panel must answer a specific operational question.
3. **Actionable Metrics** – Show KPIs that, if breached, would trigger investigation or action.
4. **Consistent Layout** – Use a standard order for panels (uptime → latency → errors → throughput → resources).
5. **Link to Runbooks** – Where possible, link directly from panels to relevant runbooks.

---

## 2. Dashboard Categories

We maintain dashboards in three main categories:

1. **Service Dashboards**
   - Focused on a single service (e.g., API, DB, Ingestion Pipeline).
   - Include uptime, latency, error rates, throughput, and key business metrics.

2. **System Dashboards**
   - Aggregate view across all services.
   - Includes system health, CPU/memory/disk usage, cluster status.

3. **Specialized Dashboards**
   - Security monitoring (login failures, unusual patterns).
   - Business KPIs (conversion rate, data ingestion speed).
   - Observability tools (Prometheus health, Alertmanager status).

---

## 3. Standard Layout Structure

We recommend this consistent structure for all dashboards:

1. **Header Row**
   - Title, environment switcher, last updated timestamp.

2. **Service Health Summary**
   - Traffic: requests per second
   - Latency: p50 / p95 / p99 response times
   - Error rate (% of 4xx and 5xx responses)

3. **Resource Usage**
   - CPU usage
   - Memory usage
   - Disk usage
   - Network I/O

4. **Dependency Health**
   - Database response time
   - External API health

5. **Business / Custom Metrics**
   - Domain-specific KPIs

6. **Alert Status**
   - Active alerts summary
   - Link to Alertmanager

7. **Links and Docs**
   - Related dashboards
   - Runbooks

---

## 4. Grafana Panel Standards

- **Time Range Defaults**: 1 hour for real-time debugging; allow easy switch to 6h/24h/7d.
- **Color Coding**:
  - Green: healthy
  - Orange: warning
  - Red: critical
- **Units**:
  - Latency: ms
  - Rates: requests/sec
  - Percentages: %
- **Annotations**:
  - Deployment events
  - Incident start/end times

---

## 5. Data Sources

Common data sources include:
- **Prometheus**: system and application metrics
- **Loki / ELK**: log aggregation
- **Tempo / Jaeger**: tracing data
- **Postgres / Memgraph**: custom business queries

---

## 6. Example Dashboards

### 6.1 MCP Tools Dashboard
_File: `docs/observability/mcp-tools-dashboard.json`_

Panels include:
- NL → Cypher request throughput
- Average Cypher execution time
- Query success/error rate
- Memgraph CPU/memory usage

### 6.2 Platform Overview Dashboard
Panels include:
- Global uptime across services
- Error budget tracking (SLO burn rate)
- Top N slowest API endpoints
- Infrastructure resource usage

### 6.3 Security Dashboard
Panels include:
- Failed login attempts over time
- Geo-distribution of login attempts
- API token misuse patterns

---

## 7. Linking Dashboards to Alerts

Each critical alert from Prometheus/Alertmanager **must** link to a corresponding Grafana dashboard panel.

Example:
```yaml
annotations:
  dashboard_url: "https://grafana.example.com/d/api-overview"
````

---

## 8. Maintenance Guidelines

* **Review Frequency**: Every quarter, prune unused panels and verify queries.
* **Performance Check**: Optimize queries for dashboard load times < 3 seconds.
* **Access Control**: Ensure sensitive dashboards (e.g., security) have restricted permissions.

---

## 9. Folder Organization in Grafana

* `/Service Dashboards`
* `/System Dashboards`
* `/Security`
* `/Business KPIs`
* `/Playground` (experimental, to be cleaned periodically)

---

## 10. Example JSON Export

Example MCP Tools Dashboard export snippet:

```json
{
  "dashboard": {
    "id": null,
    "title": "MCP Tools Dashboard",
    "panels": [
      {
        "type": "graph",
        "title": "Request Throughput",
        "targets": [
          {
            "expr": "sum(rate(mcp_requests_total[1m]))"
          }
        ]
      }
    ],
    "time": {
      "from": "now-1h",
      "to": "now"
    }
  },
  "overwrite": true
}
```

---

## 11. Future Enhancements

* Add **drill-down dashboards** for incident triage.
* Automate dashboard creation via **Terraform Grafana provider**.
* Standardize tags for panels and dashboards to improve searchability.

---

**Last updated:** 2025-08-09

```
```
