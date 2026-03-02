```markdown
# Alerting Guide

## Overview

This document defines the **alerting strategy** for the platform, ensuring timely detection and response to incidents. It covers:
- Which conditions should trigger alerts
- How alerts are routed and escalated
- How to minimize alert fatigue
- How alerts integrate with our incident response process

We primarily use **Prometheus Alertmanager** for alert evaluation and routing, with integrations into **Slack**, **Email**, and optional **PagerDuty**.

---

## 1. Alerting Principles

1. **Actionable** – Every alert must require a human action.
2. **Context-rich** – Alerts must contain enough information to start diagnosis immediately.
3. **Prioritized** – Alerts are categorized by severity to avoid noise.
4. **Consistent** – Standard naming conventions and labels for all alerts.
5. **Integrated** – Alerts link to relevant dashboards and runbooks.

---

## 2. Alert Sources

We generate alerts from:

- **Metrics** (Prometheus): Latency, error rate, resource usage, queue length.
- **Logs** (Loki, ELK, or other): Error patterns, crash loops.
- **Tracing** (Jaeger/Tempo): Abnormal latency in specific spans.
- **Synthetic monitoring**: Health check endpoints, user journey scripts.
- **Security events**: Unusual login patterns, failed auth attempts.

---

## 3. Alert Categories and Severity Levels

| Severity | Example Triggers | Response Time Target |
|----------|------------------|----------------------|
| **Critical (P1)** | Service down, data loss, unbounded error rates | Immediate (24/7) |
| **High (P2)** | High latency affecting many users, failing critical job | Within 1 hour |
| **Medium (P3)** | Non-critical service degraded, persistent warnings | Within business day |
| **Low (P4)** | Informational alerts, upcoming resource exhaustion | Scheduled work |

---

## 4. Alert Naming Conventions

Format:  
```

<ServiceName>*<MetricName>*<Condition>

````

Examples:
- `api_http_5xx_rate_high`
- `db_memgraph_high_latency`
- `queue_backlog_exceeds_threshold`

---

## 5. Standard Alert Labels

All alerts must include:

- `severity`: `critical`, `high`, `medium`, `low`
- `service`: logical service name (`api`, `db`, `queue`)
- `environment`: `prod`, `staging`, `dev`
- `runbook_url`: link to the incident runbook
- `dashboard_url`: link to Grafana/observability dashboard

---

## 6. Prometheus Alert Rules

Example `alerts.yml` snippet:
```yaml
groups:
  - name: service-health
    rules:
      - alert: api_http_5xx_rate_high
        expr: sum(rate(http_requests_total{status=~"5..", service="api"}[5m])) / sum(rate(http_requests_total{service="api"}[5m])) > 0.05
        for: 5m
        labels:
          severity: critical
          service: api
          environment: prod
          runbook_url: https://docs.example.com/runbooks/api-errors
        annotations:
          summary: "High 5xx error rate on API"
          description: "5xx error rate is above 5% for 5 minutes.\nCheck logs and recent deploys."
          dashboard_url: https://grafana.example.com/d/api-overview
````

---

## 7. Alert Routing & Notification Policy

### 7.1 Routing Rules in Alertmanager

* **Critical** → PagerDuty + Slack #ops-alerts
* **High** → Slack #ops-alerts + Email on-call engineer
* **Medium** → Slack #ops-warnings
* **Low** → Slack #ops-info

### 7.2 Escalation Policy

* If a critical alert is not acknowledged in 10 minutes → escalate to secondary on-call
* If unresolved after 30 minutes → notify engineering manager

---

## 8. Integrations

* **Slack**: Direct channel notifications with alert summary and links.
* **Email**: Backup notification channel.
* **PagerDuty**: For critical/urgent incidents with escalation.
* **Opsgenie**: Optional alternative.
* **Jira/GitHub Issues**: Automatic ticket creation for recurring alerts.

---

## 9. Example Alert Lifecycle

1. **Trigger**: Prometheus detects `db_memgraph_high_latency`.
2. **Notification**: Alertmanager sends Slack + PagerDuty alert.
3. **Acknowledgement**: On-call engineer acknowledges in PagerDuty.
4. **Investigation**: Engineer checks Grafana dashboard and tracing.
5. **Mitigation**: Roll back recent deployment or scale up resources.
6. **Resolution**: Latency returns to normal.
7. **Postmortem**: Document cause and prevention steps.

---

## 10. Avoiding Alert Fatigue

* Regularly review and prune noisy or non-actionable alerts.
* Use **for:** in Prometheus rules to avoid transient spikes.
* Group related alerts into a single notification when possible.
* Set different thresholds for staging vs. production.

---

## 11. Testing Alerts

To test without triggering real incidents:

```bash
# Inject synthetic metrics
curl -X POST http://prometheus.example.com/api/v1/series \
  -d 'http_requests_total{service="api",status="500"} 100'
```

Or temporarily lower thresholds in staging.

---

## 12. Security Alerts

Security-related alerts follow an accelerated escalation policy:

* Repeated failed logins → notify security team immediately.
* Suspicious IP activity → block via firewall automation if confirmed malicious.

---

## 13. Linking Alerts to Runbooks

Each alert **must** have a `runbook_url` label pointing to:

* Clear resolution steps
* Links to related dashboards/logs
* Common causes and quick checks

---

**Last reviewed:** 2025-08-09
