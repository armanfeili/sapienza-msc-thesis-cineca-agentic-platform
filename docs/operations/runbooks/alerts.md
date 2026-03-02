# Alerts & Monitoring

**Last Updated**: October 26, 2025  
**Review Period**: Monthly  
**Version**: 1.0.0

---

## Overview

This document defines alert definitions, thresholds, and response procedures for the Cineca Agentic Platform. Alerts are triggered when system metrics exceed defined thresholds or when critical events occur.

### Alert Severity Levels

| Severity | Response Time | On-Call Required | Examples |
|----------|---------------|------------------|----------|
| **CRITICAL** | Immediate (< 5 min) | Yes | Service down, data loss risk |
| **WARNING** | 30 minutes | No (business hours) | SLO approaching threshold |
| **INFO** | Best effort | No | Scheduled maintenance |

---

## Performance Alerts

### High Latency Alerts

#### CRITICAL: Graph Query p95 Latency Spike

**Trigger**: `graph.query` p95 latency > 2× SLO (> 1000ms) for 5 minutes

**Query**:
```sql
SELECT
  percentile_cont(0.95) WITHIN GROUP (ORDER BY execution_time_ms) AS p95_latency
FROM query_metrics
WHERE tool_name = 'graph.query'
  AND timestamp > NOW() - INTERVAL '5 minutes'
HAVING p95_latency > 1000;
```

**Impact**:
- User-facing queries slow or timing out
- Cascading delays to downstream tools (graph.secure_query)

**Response**:
1. Check active queries: `SHOW QUERIES` (Memgraph)
2. Identify slow queries: Filter by `execution_time_ms > 1000`
3. Kill slow queries: `TERMINATE TRANSACTIONS "transaction_id"`
4. Check database load: CPU, memory, disk I/O
5. Scale database if sustained high load

**Escalation**: Database team after 15 minutes

---

#### WARNING: Model Tools High Latency

**Trigger**: `model.test` p95 latency > 1.5× SLO (> 4500ms) for 10 minutes

**Query**:
```sql
SELECT
  percentile_cont(0.95) WITHIN GROUP (ORDER BY execution_time_ms) AS p95_latency
FROM tool_invocations
WHERE tool_name = 'model.test'
  AND timestamp > NOW() - INTERVAL '10 minutes'
HAVING p95_latency > 4500;
```

**Impact**:
- Slower model testing
- Delayed feedback to users

**Response**:
1. Check model provider API status (OpenAI, Anthropic, etc.)
2. Review network latency to external APIs
3. Check rate limiting on provider side
4. Consider switching to backup provider

**Escalation**: Infrastructure team if latency > 10s

---

### Rate Limiting Alerts

#### CRITICAL: Rate Limit Breach (Tool Class)

**Trigger**: > 10 rate limit errors (429) per minute for any tool class

**Query**:
```sql
SELECT
  tool_class,
  COUNT(*) AS rate_limit_errors
FROM tool_invocations
WHERE status_code = 429
  AND timestamp > NOW() - INTERVAL '1 minute'
GROUP BY tool_class
HAVING COUNT(*) > 10;
```

**Impact**:
- Users blocked from critical operations
- Potential service degradation

**Response**:
1. Identify affected tool class (Graph, Model, etc.)
2. Check if legitimate traffic spike or abuse
3. Increase rate limits if legitimate traffic
4. Block abusive IP addresses if attack
5. Notify users of temporary degradation

**Escalation**: Security team if suspected attack

---

#### WARNING: Approaching Rate Limit

**Trigger**: > 80% of rate limit consumed for any user/tenant

**Query**:
```sql
SELECT
  user_id,
  tenant_id,
  tool_class,
  request_count,
  rate_limit,
  (request_count * 100.0 / rate_limit) AS usage_pct
FROM rate_limit_usage
WHERE timestamp > NOW() - INTERVAL '1 minute'
  AND (request_count * 100.0 / rate_limit) > 80
ORDER BY usage_pct DESC;
```

**Impact**:
- User approaching limits, may be blocked soon

**Response**:
1. Notify user via email/webhook
2. Suggest optimization (batching, caching)
3. Review if user needs higher tier
4. Monitor for continued growth

**Escalation**: None (informational)

---

### Error Rate Alerts

#### CRITICAL: High Error Rate

**Trigger**: Error rate > 5% for 5 minutes (any tool class)

**Query**:
```sql
SELECT
  tool_class,
  COUNT(*) FILTER (WHERE status = 'error') * 100.0 / COUNT(*) AS error_rate_pct,
  COUNT(*) AS total_requests
FROM tool_invocations
WHERE timestamp > NOW() - INTERVAL '5 minutes'
GROUP BY tool_class
HAVING error_rate_pct > 5;
```

**Impact**:
- Widespread failures affecting users
- Potential data integrity issues

**Response**:
1. Check error distribution by error code
2. Review recent deployments (rollback if needed)
3. Check dependent service health (Postgres, Redis, Memgraph)
4. Review error logs for common patterns
5. Enable circuit breakers if external dependency failing

**Escalation**: Engineering lead after 10 minutes

---

#### WARNING: Error Rate Above SLO

**Trigger**: Error rate > SLO threshold for 10 minutes

**Query**:
```sql
SELECT
  tool_name,
  COUNT(*) FILTER (WHERE status = 'error') * 100.0 / COUNT(*) AS error_rate_pct,
  target_slo
FROM tool_invocations
JOIN slo_targets ON tool_invocations.tool_name = slo_targets.tool_name
WHERE timestamp > NOW() - INTERVAL '10 minutes'
GROUP BY tool_name, target_slo
HAVING error_rate_pct > target_slo;
```

**Impact**:
- Consuming error budget
- SLO compliance at risk

**Response**:
1. Identify error patterns (auth, timeout, validation)
2. Review recent changes
3. Check error budget remaining
4. Create incident report if budget exhausted

**Escalation**: None (monitoring)

---

## Availability Alerts

### Service Health Alerts

#### CRITICAL: Service Down

**Trigger**: Health check fails for > 1 minute

**Query**:
```sql
SELECT
  component_name,
  status,
  last_check
FROM health_checks
WHERE status = 'down'
  AND last_check > NOW() - INTERVAL '1 minute';
```

**Impact**:
- Service unavailable to users
- Complete outage or partial degradation

**Response**:
1. Check service status: `systemctl status cineca-api`
2. Review service logs: `journalctl -u cineca-api -n 100`
3. Restart service if crashed: `systemctl restart cineca-api`
4. Check dependent services (Postgres, Redis, Memgraph)
5. Review resource exhaustion (OOM, disk full)

**Escalation**: Immediate page to on-call

---

#### CRITICAL: Database Connection Failure

**Trigger**: Postgres/Redis/Memgraph connection errors > 10/min

**Query**:
```sql
SELECT
  database_type,
  COUNT(*) AS connection_errors
FROM database_errors
WHERE error_type = 'connection_failed'
  AND timestamp > NOW() - INTERVAL '1 minute'
GROUP BY database_type
HAVING COUNT(*) > 10;
```

**Impact**:
- Unable to read/write data
- Service degradation or complete failure

**Response**:
1. Check database service status
2. Review connection pool exhaustion
3. Check network connectivity
4. Review database resource usage (CPU, memory, disk)
5. Restart database if unresponsive (use failover if available)

**Escalation**: Database team immediately

---

### Component Degradation

#### WARNING: Component Degraded

**Trigger**: Component health status = 'degraded' for > 5 minutes

**Query**:
```sql
SELECT
  component_name,
  status,
  details
FROM health_checks
WHERE status = 'degraded'
  AND last_check > NOW() - INTERVAL '5 minutes';
```

**Impact**:
- Reduced performance
- Potential escalation to outage

**Response**:
1. Identify degraded component
2. Review component-specific metrics
3. Check if auto-healing triggered
4. Monitor for improvement or escalation

**Escalation**: After 15 minutes if not improving

---

## Security Alerts

### Authentication Alerts

#### CRITICAL: High Authentication Failure Rate

**Trigger**: > 100 auth failures/min from single IP or user

**Query**:
```sql
SELECT
  ip_address,
  user_id,
  COUNT(*) AS auth_failures
FROM auth_events
WHERE status = 'failed'
  AND timestamp > NOW() - INTERVAL '1 minute'
GROUP BY ip_address, user_id
HAVING COUNT(*) > 100;
```

**Impact**:
- Potential brute force attack
- Account compromise risk

**Response**:
1. Block IP address immediately
2. Force password reset for affected users
3. Review auth logs for patterns
4. Enable MFA for affected accounts
5. Notify security team

**Escalation**: Security team immediately

---

#### WARNING: Invalid Token Usage

**Trigger**: > 50 invalid token errors/min

**Query**:
```sql
SELECT
  COUNT(*) AS invalid_token_errors
FROM auth_events
WHERE error_type = 'invalid_token'
  AND timestamp > NOW() - INTERVAL '1 minute'
HAVING COUNT(*) > 50;
```

**Impact**:
- Expired or revoked tokens in use
- Potential token theft

**Response**:
1. Review token expiration policies
2. Check for token leakage
3. Notify affected users to refresh tokens
4. Consider rotating signing keys if compromise suspected

**Escalation**: Security team if sustained

---

### Data Access Alerts

#### CRITICAL: Unauthorized Data Access Attempt

**Trigger**: > 10 403 Forbidden errors/min for admin endpoints

**Query**:
```sql
SELECT
  user_id,
  tenant_id,
  endpoint,
  COUNT(*) AS forbidden_attempts
FROM access_logs
WHERE status_code = 403
  AND endpoint LIKE '/admin/%'
  AND timestamp > NOW() - INTERVAL '1 minute'
GROUP BY user_id, tenant_id, endpoint
HAVING COUNT(*) > 10;
```

**Impact**:
- Potential privilege escalation attempt
- Security breach risk

**Response**:
1. Block user immediately
2. Review audit logs for affected user
3. Check for compromised credentials
4. Notify security team
5. Investigate lateral movement

**Escalation**: Security team immediately

---

## Capacity Alerts

### Resource Utilization Alerts

#### CRITICAL: High CPU Usage

**Trigger**: CPU > 90% for 5 minutes

**Query**:
```bash
# Prometheus
avg_over_time(node_cpu_seconds_total{mode="idle"}[5m]) < 10
```

**Impact**:
- Service slowdowns
- Request timeouts
- Potential cascading failures

**Response**:
1. Identify CPU-intensive processes: `top`
2. Check for query storms or infinite loops
3. Kill problematic processes if needed
4. Scale horizontally (add instances)
5. Review recent deployments

**Escalation**: Infrastructure team after 10 minutes

---

#### CRITICAL: High Memory Usage

**Trigger**: Memory > 90% for 5 minutes

**Query**:
```bash
# Prometheus
(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) > 0.9
```

**Impact**:
- OOM killer may terminate processes
- Service instability

**Response**:
1. Identify memory-intensive processes: `ps aux --sort=-%mem`
2. Check for memory leaks
3. Restart leaking services
4. Scale vertically (add memory) or horizontally
5. Review query result set sizes

**Escalation**: Infrastructure team immediately if OOM risk

---

#### WARNING: Disk Space Low

**Trigger**: Disk usage > 80%

**Query**:
```bash
# Prometheus
(1 - (node_filesystem_avail_bytes / node_filesystem_size_bytes)) > 0.8
```

**Impact**:
- Unable to write logs or data
- Service failures

**Response**:
1. Identify large files: `du -sh /* | sort -hr`
2. Clean up old logs: `logrotate -f /etc/logrotate.conf`
3. Archive old data
4. Increase disk size

**Escalation**: Infrastructure team if > 90%

---

### Throughput Alerts

#### WARNING: High Request Rate

**Trigger**: Request rate > 2× average for 10 minutes

**Query**:
```sql
SELECT
  COUNT(*) AS current_rps,
  (SELECT AVG(rps) FROM hourly_metrics WHERE timestamp > NOW() - INTERVAL '24 hours') AS avg_rps
FROM tool_invocations
WHERE timestamp > NOW() - INTERVAL '1 minute'
HAVING current_rps > avg_rps * 2;
```

**Impact**:
- Potential capacity limits
- Increased latency

**Response**:
1. Verify if legitimate traffic (marketing campaign, etc.)
2. Check for DDoS attack
3. Enable rate limiting if needed
4. Scale horizontally
5. Enable caching

**Escalation**: Infrastructure team if sustained > 30 min

---

## Data Integrity Alerts

### Backup Alerts

#### CRITICAL: Backup Failed

**Trigger**: Backup job failed

**Query**:
```sql
SELECT
  backup_id,
  status,
  error_message
FROM backups
WHERE status = 'failed'
  AND created_at > NOW() - INTERVAL '24 hours';
```

**Impact**:
- Data loss risk if disaster occurs
- Compliance violations

**Response**:
1. Review backup job logs
2. Check disk space on backup destination
3. Retry backup manually
4. Escalate if repeated failures
5. Notify compliance team

**Escalation**: Data team immediately

---

#### WARNING: Backup Size Anomaly

**Trigger**: Backup size differs > 30% from average

**Query**:
```sql
SELECT
  backup_id,
  size_bytes,
  (SELECT AVG(size_bytes) FROM backups WHERE created_at > NOW() - INTERVAL '7 days') AS avg_size,
  ABS(size_bytes - (SELECT AVG(size_bytes) FROM backups WHERE created_at > NOW() - INTERVAL '7 days')) * 100.0 / 
    (SELECT AVG(size_bytes) FROM backups WHERE created_at > NOW() - INTERVAL '7 days') AS size_diff_pct
FROM backups
WHERE created_at > NOW() - INTERVAL '24 hours'
HAVING size_diff_pct > 30;
```

**Impact**:
- Potential data corruption or unexpected growth

**Response**:
1. Verify backup integrity
2. Check for data corruption
3. Review recent data ingestion
4. Investigate anomaly

**Escalation**: Data team if corruption suspected

---

## Alert Configuration

### Prometheus Alert Rules

Example alert rule configuration:

```yaml
groups:
  - name: mcp_tools
    interval: 30s
    rules:
      - alert: HighGraphQueryLatency
        expr: histogram_quantile(0.95, rate(graph_query_duration_seconds_bucket[5m])) > 1.0
        for: 5m
        labels:
          severity: critical
          component: graph_tools
        annotations:
          summary: "High graph query latency"
          description: "p95 latency for graph.query is {{ $value }}s (threshold: 1s)"
          runbook: "https://docs.cineca.ai/ops/runbooks/troubleshooting-tools.md#graph-query-timeouts"

      - alert: HighErrorRate
        expr: (rate(tool_invocations_total{status="error"}[5m]) / rate(tool_invocations_total[5m])) > 0.05
        for: 5m
        labels:
          severity: critical
          component: api
        annotations:
          summary: "High error rate"
          description: "Error rate is {{ $value | humanizePercentage }} (threshold: 5%)"
          runbook: "https://docs.cineca.ai/ops/runbooks/troubleshooting-tools.md"

      - alert: ServiceDown
        expr: up{job="cineca-api"} == 0
        for: 1m
        labels:
          severity: critical
          component: api
        annotations:
          summary: "Service down"
          description: "Cineca API is down"
          runbook: "https://docs.cineca.ai/ops/runbooks/troubleshooting-tools.md"

      - alert: RateLimitBreach
        expr: rate(tool_invocations_total{status_code="429"}[1m]) > 10
        for: 2m
        labels:
          severity: critical
          component: rate_limiter
        annotations:
          summary: "Rate limit breaches"
          description: "{{ $value }} rate limit errors/min (threshold: 10)"
          runbook: "https://docs.cineca.ai/ops/runbooks/troubleshooting-tools.md#rate-limiting"

      - alert: DatabaseConnectionErrors
        expr: rate(database_errors_total{error_type="connection_failed"}[1m]) > 10
        for: 1m
        labels:
          severity: critical
          component: database
        annotations:
          summary: "Database connection failures"
          description: "{{ $value }} connection errors/min (threshold: 10)"
          runbook: "https://docs.cineca.ai/ops/runbooks/troubleshooting-tools.md"

      - alert: HighCPU
        expr: 100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 90
        for: 5m
        labels:
          severity: critical
          component: infrastructure
        annotations:
          summary: "High CPU usage"
          description: "CPU usage is {{ $value }}% (threshold: 90%)"
          runbook: "https://docs.cineca.ai/ops/runbooks/troubleshooting-tools.md"

      - alert: LowDiskSpace
        expr: (1 - (node_filesystem_avail_bytes / node_filesystem_size_bytes)) * 100 > 80
        for: 5m
        labels:
          severity: warning
          component: infrastructure
        annotations:
          summary: "Low disk space"
          description: "Disk usage is {{ $value }}% (threshold: 80%)"
          runbook: "https://docs.cineca.ai/ops/runbooks/troubleshooting-tools.md"

      - alert: BackupFailed
        expr: backup_job_status{status="failed"} == 1
        for: 1m
        labels:
          severity: critical
          component: data
        annotations:
          summary: "Backup failed"
          description: "Backup job {{ $labels.backup_id }} failed"
          runbook: "https://docs.cineca.ai/ops/runbooks/troubleshooting-tools.md"
```

---

## Alert Routing

### Notification Channels

| Severity | Channels | Routing |
|----------|----------|---------|
| **CRITICAL** | PagerDuty, Slack (#incidents), Email | On-call engineer |
| **WARNING** | Slack (#alerts), Email | Team channel (business hours) |
| **INFO** | Slack (#monitoring) | No action required |

### PagerDuty Integration

```yaml
# alertmanager.yml
route:
  receiver: 'default'
  group_by: ['alertname', 'severity']
  group_wait: 10s
  group_interval: 5m
  repeat_interval: 3h
  routes:
    - match:
        severity: critical
      receiver: pagerduty
    - match:
        severity: warning
      receiver: slack
    - match:
        severity: info
      receiver: slack-info

receivers:
  - name: 'pagerduty'
    pagerduty_configs:
      - service_key: '<pagerduty_service_key>'
        description: '{{ .CommonAnnotations.summary }}'
        details:
          firing: '{{ template "pagerduty.default.instances" . }}'
          resolved: '{{ template "pagerduty.default.instances" . }}'

  - name: 'slack'
    slack_configs:
      - api_url: '<slack_webhook_url>'
        channel: '#alerts'
        text: '{{ range .Alerts }}{{ .Annotations.description }}{{ end }}'

  - name: 'slack-info'
    slack_configs:
      - api_url: '<slack_webhook_url>'
        channel: '#monitoring'
        text: '{{ range .Alerts }}{{ .Annotations.description }}{{ end }}'
```

---

## Alert Response Procedures

### General Response Workflow

1. **Acknowledge Alert**: Acknowledge in PagerDuty/Slack within 5 minutes
2. **Assess Impact**: Determine user impact (partial/complete outage)
3. **Follow Runbook**: Use runbook link in alert annotation
4. **Mitigate**: Apply immediate mitigation (restart, scale, block)
5. **Monitor**: Verify alert clears
6. **Document**: Create incident report if CRITICAL
7. **Post-Mortem**: Schedule review for CRITICAL incidents

### Incident Severity Matrix

| User Impact | Duration | Severity | Example |
|-------------|----------|----------|---------|
| Complete outage | Any | SEV-1 | Service down |
| Partial outage | > 1 hour | SEV-2 | High latency |
| Degradation | > 4 hours | SEV-3 | Slow queries |
| No impact | Any | SEV-4 | Warning alerts |

---

## Alert Suppression

### Maintenance Windows

Suppress alerts during planned maintenance:

```yaml
# alertmanager.yml
inhibit_rules:
  - source_match:
      alertname: MaintenanceWindow
    target_match_re:
      severity: critical|warning
    equal: ['instance']
```

### Alert Fatigue Prevention

- **Grouping**: Group related alerts (e.g., all database alerts)
- **Deduplication**: Suppress duplicate alerts within 3 hours
- **Throttling**: Limit repeat notifications to 3 hours
- **Smart Routing**: Route warnings to Slack only during business hours

---

## Dashboards

### Recommended Grafana Dashboards

1. **Service Health Dashboard**:
   - Component status (Postgres, Redis, Memgraph, API)
   - Request rate, error rate, latency
   - Active alerts

2. **Tool Performance Dashboard**:
   - Per-tool latency (p50, p95, p99)
   - Request count by tool
   - Error breakdown by tool

3. **Capacity Dashboard**:
   - CPU, memory, disk usage
   - Request throughput
   - Database connections

4. **Security Dashboard**:
   - Authentication failures
   - Rate limit breaches
   - 403 Forbidden errors
   - Suspicious IP activity

---

## Alert Tuning

### Review Process

- **Weekly**: Review alert volume, false positive rate
- **Monthly**: Adjust thresholds based on historical data
- **Quarterly**: Review alert effectiveness, deprecate unused alerts

### Tuning Guidelines

- **False Positives**: If > 50% of alerts are false positives, increase threshold
- **Alert Fatigue**: If > 100 alerts/day, consolidate or suppress noisy alerts
- **Coverage Gaps**: Add alerts for uncovered failure modes

---

**See Also**:
- [SLOs](./slos.md) - Service level objectives
- [Troubleshooting Guide](./troubleshooting-tools.md) - Diagnostic procedures
- [Architecture](../../architecture.md) - System design
