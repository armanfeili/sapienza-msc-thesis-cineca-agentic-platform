# Platform Health Monitoring

Complete monitoring setup for the Cineca Agentic Platform infrastructure.

## Overview

This monitoring stack provides:

- **Real-time health tracking** via Prometheus metrics
- **Visual dashboards** in Grafana
- **Automated alerts** for critical issues
- **Historical analysis** of component performance

## Components Monitored

### Critical (Required for Operations)
- **PostgreSQL** - Primary database
- **Redis** - Cache and job storage
- **App** - FastAPI application
- **Workers** - Background job processors

### Important (Operational Impact)
- **Providers** - LLM provider health
- **Prometheus** - Metrics collection
- **Grafana** - Visualization

### Informational (Optional)
- **Memgraph** - Graph database (non-critical)
- **Ollama** - Local LLM server

## Quick Start

### 1. Access Dashboards

**Grafana**: http://localhost:3000
- Username: `admin`
- Password: `admin` (change on first login)

**Prometheus**: http://localhost:9090

### 2. Import Health Dashboard

The health dashboard is automatically provisioned at:
- **Dashboard**: Platform Health Overview
- **Path**: `/ops/grafana/dashboards/health-overview.json`
- **URL**: http://localhost:3000/d/health-overview

### 3. View Alerts

**Prometheus Alerts**: http://localhost:9090/alerts
**Grafana Alerting**: http://localhost:3000/alerting/list

## Metrics Available

### Health Status Metrics

```promql
# Component health status (0=OK, 1=Degraded, 2=Error)
health_component_status{component="postgres|redis|app|providers|memgraph"}

# Component latency in milliseconds
health_component_latency_ms{component="postgres|redis|providers|prometheus|grafana"}

# Overall system readiness (0=not ready, 1=ready)
health_readiness

# Overall system liveness (0=not live, 1=live)
health_liveness
```

### Background Job Metrics

```promql
# Job execution count and duration
background_job_duration_seconds_count{job="health-checks|provider-health-checks"}
background_job_duration_seconds_sum{job="health-checks|provider-health-checks"}

# Job execution histogram
background_job_duration_seconds_bucket{job="health-checks"}
```

### Provider Metrics

```promql
# Provider health information
health_provider_info{provider_id="ollama-local", status="healthy|unhealthy"}

# Provider check latency
health_provider_check_duration_seconds
```

## Alert Rules

### Critical Alerts (Immediate Action Required)

| Alert | Condition | Duration | Action |
|-------|-----------|----------|--------|
| **PostgreSQLDown** | status == ERROR | 2 minutes | Check database connectivity, logs |
| **RedisDown** | status == ERROR | 2 minutes | Check cache connectivity, logs |
| **AppDown** | status == ERROR | 1 minute | Check application logs, restart |

### Warning Alerts (Investigation Needed)

| Alert | Condition | Duration | Action |
|-------|-----------|----------|--------|
| **PostgreSQLDegraded** | status == DEGRADED | 5 minutes | Check database performance |
| **AllProvidersUnhealthy** | All providers down | 5 minutes | Check provider connectivity |
| **PostgreSQLHighLatency** | latency > 500ms | 5 minutes | Investigate database load |
| **RedisHighLatency** | latency > 100ms | 5 minutes | Investigate cache performance |

### Info Alerts (Awareness Only)

| Alert | Condition | Duration | Action |
|-------|-----------|----------|--------|
| **MemgraphDegraded** | status != OK | 15 minutes | Optional: Investigate Memgraph |
| **MonitoringServicesDegraded** | Prometheus/Grafana down | 10 minutes | Check monitoring stack |

## Dashboard Panels

### 1. Overall System Health
- Single stat showing overall health percentage
- Green (>95%), Yellow (80-95%), Red (<80%)

### 2. Component Health Status
- Time series of all component health over time
- Shows transitions between OK/Degraded/Error states

### 3. Component Latency
- Time series of health check latencies
- Helps identify performance degradation

### 4. Individual Component Cards
- Stat panels for each critical component
- Color-coded: Green (OK), Yellow (Degraded), Red (Error)

### 5. Provider Health Table
- Detailed table of provider status
- Shows provider ID, status, last check time

### 6. Background Job Execution
- Rate of job executions (success vs error)
- Helps monitor automation health

## Configuration

### Health Check Intervals

```bash
# In docker-compose.yml or .env
HEALTHCHECK_INTERVAL_SECONDS=30              # General health checks
PROVIDER_HEALTH_CHECK_INTERVAL=60            # Provider health checks
```

### Health Check Timeouts

```bash
HEALTH_TIMEOUT_MS=3000                       # General timeout
HEALTH_DB_TIMEOUT_MS=3000                    # Database timeout
HEALTH_CACHE_TIMEOUT_MS=1000                 # Cache timeout
```

### Alert Notification Channels

Configure in Grafana UI:
1. Go to **Alerting** → **Contact points**
2. Add channels: Email, Slack, PagerDuty, etc.
3. Link to alert rules

### Prometheus Alert Manager

Edit `ops/prometheus/alertmanager.yml`:

```yaml
route:
  receiver: 'default'
  group_by: ['alertname', 'severity']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  routes:
    - match:
        severity: critical
      receiver: 'pagerduty'
    - match:
        severity: warning
      receiver: 'slack'

receivers:
  - name: 'default'
    email_configs:
      - to: 'ops@example.com'
  - name: 'slack'
    slack_configs:
      - api_url: 'YOUR_SLACK_WEBHOOK'
        channel: '#alerts'
  - name: 'pagerduty'
    pagerduty_configs:
      - service_key: 'YOUR_PAGERDUTY_KEY'
```

## Troubleshooting

### Metrics Not Appearing

1. **Check metrics endpoint**:
   ```bash
   curl http://localhost:8000/metrics
   ```

2. **Verify Prometheus scraping**:
   ```bash
   # Check targets in Prometheus UI
   open http://localhost:9090/targets
   ```

3. **Check Prometheus config**:
   ```bash
   docker exec prometheus cat /etc/prometheus/prometheus.yml
   ```

### Dashboard Not Loading

1. **Verify Grafana is running**:
   ```bash
   docker ps | grep grafana
   curl http://localhost:3000/api/health
   ```

2. **Check dashboard provisioning**:
   ```bash
   docker exec grafana ls /etc/grafana/provisioning/dashboards
   ```

3. **Re-import dashboard**:
   - Go to Grafana → Dashboards → Import
   - Upload `/ops/grafana/dashboards/health-overview.json`

### Alerts Not Firing

1. **Check alert rules loaded**:
   ```bash
   curl http://localhost:9090/api/v1/rules
   ```

2. **Verify alert conditions**:
   - Go to Prometheus → Alerts
   - Check if metric exists: `health_component_status{component="postgres"}`

3. **Test alert manually**:
   ```promql
   # Query in Prometheus to simulate alert condition
   health_component_status{component="postgres"} == 2
   ```

## Best Practices

### 1. Regular Review
- Check dashboards daily
- Review alerts weekly
- Adjust thresholds based on actual performance

### 2. Alert Fatigue Prevention
- Don't alert on informational components (Memgraph, monitoring services)
- Use appropriate durations (don't alert on transient issues)
- Group related alerts

### 3. Runbook Maintenance
- Keep runbooks up-to-date
- Document common resolution steps
- Include escalation paths

### 4. Performance Baselines
- Establish normal latency ranges
- Track trends over time
- Adjust thresholds seasonally if needed

## Advanced Queries

### Component Availability Over Time

```promql
# Availability percentage (last 24h)
avg_over_time(
  (health_component_status{component="postgres"} == 0)[24h:]
)
```

### P95 Health Check Latency

```promql
histogram_quantile(0.95,
  rate(health_check_duration_seconds_bucket[5m])
)
```

### Provider Health Trend

```promql
# Percentage of healthy providers
(
  health_provider_count{status="healthy"} /
  health_provider_count
) * 100
```

### Background Job Success Rate

```promql
# Success rate (last 1h)
sum(rate(background_job_duration_seconds_count{status="ok"}[1h]))
/
sum(rate(background_job_duration_seconds_count[1h]))
```

## Maintenance

### Updating Alert Rules

1. Edit `/ops/prometheus/rules/health-alerts.yml`
2. Reload Prometheus:
   ```bash
   docker exec prometheus kill -HUP 1
   # Or restart
   docker compose restart prometheus
   ```
3. Verify rules loaded:
   ```bash
   curl http://localhost:9090/api/v1/rules | jq '.data.groups[].name'
   ```

### Updating Dashboards

1. Export from Grafana UI (Share → Export)
2. Save to `/ops/grafana/dashboards/health-overview.json`
3. Commit to repository
4. Redeploy or wait for provisioning

### Backup & Recovery

**Backup Grafana dashboards**:
```bash
docker exec grafana backup-tool export --output /backups/
```

**Backup Prometheus data**:
```bash
docker exec prometheus tar czf /prometheus/backup.tar.gz /prometheus/data
```

## Integration Examples

### Slack Notifications

```python
# In alert handler
import requests

def send_slack_alert(alert_name, severity, description):
    webhook = "YOUR_SLACK_WEBHOOK"
    message = {
        "text": f"🚨 {severity.upper()}: {alert_name}",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{alert_name}*\n{description}"
                }
            }
        ]
    }
    requests.post(webhook, json=message)
```

### Custom Alert Actions

```python
# In alert handler
from db.postgres_control.repositories import provider_repo

async def handle_provider_down_alert(provider_id):
    # Auto-restart unhealthy provider
    health = await check_provider_health(provider_id)
    if not health['ok']:
        logger.warning(f"Provider {provider_id} unhealthy, attempting restart")
        # Trigger provider restart logic
        await restart_provider(provider_id)
```

## Support

For issues or questions:
1. Check logs: `docker compose logs app prometheus grafana`
2. Review runbooks: `/docs/runbooks/`
3. Contact platform team

---

**Last Updated**: 2025-10-31  
**Maintained By**: Platform Team  
**Version**: 1.0
