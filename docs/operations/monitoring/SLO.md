# Service Level Objectives (SLOs) - Cineca Agentic Platform

**Version**: 1.0  
**Last Updated**: October 27, 2025  
**Review Cycle**: Quarterly

---

## Executive Summary

This document defines Service Level Objectives (SLOs) for the Cineca Agentic Platform. SLOs are measurable targets for service quality that help balance reliability with development velocity. They are measured using Service Level Indicators (SLIs) and are enforced through alerting rules in Prometheus.

### SLO Philosophy

- **User-centric**: SLOs reflect user experience, not internal metrics
- **Achievable**: Targets allow for maintenance windows and deployments
- **Actionable**: Breaches trigger specific response procedures
- **Error budget-based**: Allows controlled risk-taking in development

---

## SLO Classes

We define three classes of service guarantees:

| Class | Availability | Latency (p95) | Error Rate | Use Case |
|-------|-------------|---------------|------------|----------|
| **Critical** | 99.9% | < 500ms | < 0.1% | Core API endpoints, authentication |
| **Standard** | 99.5% | < 2s | < 1% | Agent runs, tool invocations |
| **Best Effort** | 95% | < 10s | < 5% | Background jobs, batch operations |

---

## SLO Definitions

### 1. API Availability SLO

**Class**: Critical  
**SLI**: Percentage of successful HTTP requests (non-5xx responses)  
**Target**: 99.9% over 30-day rolling window  
**Error Budget**: 0.1% = 43.2 minutes downtime per month

#### Measurement

```promql
# SLI: Availability percentage
(
  sum(rate(http_requests_total{status!~"5.."}[30d]))
  /
  sum(rate(http_requests_total[30d]))
) * 100
```

#### Exclusions
- Planned maintenance windows (< 4 hours/month, announced 7 days prior)
- Client errors (4xx responses)
- Requests to `/metrics` and `/docs` endpoints

#### Alert Thresholds
- **Warning**: Error budget 50% consumed (21.6 min downtime)
- **Critical**: Error budget 80% consumed (34.6 min downtime)
- **Emergency**: Availability < 99% over last 1 hour

#### Response Procedures
1. **Warning**: Review error logs, identify trends
2. **Critical**: Incident declared, page on-call engineer
3. **Emergency**: Activate incident response team, halt deployments

---

### 2. API Latency SLO

**Class**: Critical (endpoints), Standard (bulk operations)  
**SLI**: 95th percentile response time  
**Targets**:
- Critical endpoints: p95 < 500ms, p99 < 1s
- Standard endpoints: p95 < 2s, p99 < 5s

#### Measurement

```promql
# SLI: p95 latency for critical endpoints
histogram_quantile(0.95,
  sum(rate(http_request_duration_seconds_bucket{
    path=~"/v1/health.*|/v1/auth.*|/v1/user/me"
  }[30d])) by (le)
)

# SLI: p95 latency for standard endpoints
histogram_quantile(0.95,
  sum(rate(http_request_duration_seconds_bucket{
    path!~"/v1/health.*|/v1/auth.*|/v1/metrics"
  }[30d])) by (le)
)
```

#### Alert Thresholds
- **Warning**: p95 > target for 10 minutes
- **Critical**: p95 > 2x target for 5 minutes

#### Response Procedures
1. Check database query performance
2. Review LLM provider latency
3. Analyze request patterns for spikes
4. Consider scaling up compute resources

---

### 3. Agent Run Success Rate SLO

**Class**: Standard  
**SLI**: Percentage of successful agent runs  
**Target**: 99% success rate over 7-day rolling window  
**Error Budget**: 1% = ~100 failed runs per 10,000 runs

#### Measurement

```promql
# SLI: Agent run success rate
(
  sum(rate(agent_runs_total{status="success"}[7d]))
  /
  sum(rate(agent_runs_total[7d]))
) * 100
```

#### Exclusions
- User-induced errors (invalid input, auth failures)
- Intentional test failures
- Agent runs during canary deployments (< 5% traffic)

#### Alert Thresholds
- **Warning**: Success rate < 99.5% over 1 hour
- **Critical**: Success rate < 98% over 1 hour
- **Emergency**: Success rate < 95% over 15 minutes

---

### 4. Agent Run Latency SLO

**Class**: Standard  
**SLI**: 95th percentile agent run duration  
**Target**: p95 < 30s, p99 < 120s  
**Measurement Window**: 24 hours

#### Measurement

```promql
# SLI: p95 agent run duration
histogram_quantile(0.95,
  sum(rate(agent_run_duration_seconds_bucket[24h])) by (le, agent_type)
)
```

#### Alert Thresholds
- **Warning**: p95 > 45s for 30 minutes
- **Critical**: p95 > 120s for 15 minutes

#### Response Procedures
1. Check LLM provider performance
2. Review tool execution times
3. Analyze agent complexity (steps, iterations)
4. Consider caching frequently accessed data

---

### 5. LLM Call Success Rate SLO

**Class**: Standard  
**SLI**: Percentage of successful LLM API calls  
**Target**: 98% success rate over 24 hours  
**Error Budget**: 2% = 29 minutes of continuous failures per day

#### Measurement

```promql
# SLI: LLM call success rate
(
  sum(rate(llm_calls_total{status!="error"}[24h]))
  /
  sum(rate(llm_calls_total[24h]))
) * 100
```

#### Exclusions
- Rate limit errors when client backoff is working
- Intentional test errors
- LLM provider scheduled maintenance (if announced)

#### Alert Thresholds
- **Warning**: Success rate < 99% over 10 minutes
- **Critical**: Success rate < 95% over 5 minutes

---

### 6. LLM Call Latency SLO

**Class**: Standard  
**SLI**: 95th percentile LLM response time  
**Target**: p95 < 10s, p99 < 30s  
**Measurement Window**: 1 hour

#### Measurement

```promql
# SLI: p95 LLM call duration
histogram_quantile(0.95,
  sum(rate(llm_call_duration_seconds_bucket[1h])) by (le, model, provider)
)
```

#### Alert Thresholds
- **Warning**: p95 > 20s for 15 minutes
- **Critical**: p95 > 60s for 10 minutes

---

### 7. Tool Invocation Success Rate SLO

**Class**: Standard  
**SLI**: Percentage of successful tool invocations  
**Target**: 97% success rate over 24 hours  
**Error Budget**: 3%

#### Measurement

```promql
# SLI: Tool invocation success rate
(
  sum(rate(tools_invocations_total{status!="failed"}[24h])) by (tool_name)
  /
  sum(rate(tools_invocations_total[24h])) by (tool_name)
) * 100
```

#### Exclusions
- Invalid input errors (user error)
- Permission denials (authz working as designed)
- Tools marked as experimental/beta

#### Alert Thresholds
- **Warning**: Success rate < 98% for specific tool over 30 minutes
- **Critical**: Success rate < 90% for any tool over 15 minutes

---

### 8. Database Query Latency SLO

**Class**: Critical  
**SLI**: 95th percentile query duration  
**Targets**:
- PostgreSQL: p95 < 100ms, p99 < 500ms
- Memgraph: p95 < 200ms, p99 < 1s
- Redis: p95 < 10ms, p99 < 50ms

#### Measurement

```promql
# PostgreSQL
histogram_quantile(0.95,
  sum(rate(pg_stat_statements_mean_time_seconds_bucket[1h])) by (le)
)

# Memgraph
histogram_quantile(0.95,
  sum(rate(memgraph_query_duration_seconds_bucket[1h])) by (le)
)

# Redis
histogram_quantile(0.95,
  sum(rate(redis_command_duration_seconds_bucket[1h])) by (le)
)
```

---

### 9. Rate Limiting Accuracy SLO

**Class**: Best Effort  
**SLI**: Percentage of legitimate requests NOT rate limited  
**Target**: > 99.9% false positive rate < 0.1%

#### Measurement

```promql
# SLI: False positive rate
(
  sum(rate(rate_limit_requests_total{status="rejected",reason="false_positive"}[24h]))
  /
  sum(rate(rate_limit_requests_total{status="rejected"}[24h]))
) * 100
```

#### Alert Thresholds
- **Warning**: False positive rate > 0.5%
- **Critical**: False positive rate > 2%

---

### 10. Data Durability SLO

**Class**: Critical  
**SLI**: Percentage of write operations successfully persisted  
**Target**: 99.99% durability (no data loss)

#### Measurement

```promql
# SLI: Write success rate
(
  sum(rate(db_writes_total{status="success"}[30d]))
  /
  sum(rate(db_writes_total[30d]))
) * 100
```

#### Exclusions
- Writes rejected due to validation errors
- Writes rejected due to duplicate key constraints (expected)

---

## Error Budget Policy

### Error Budget Calculation

```
Error Budget = (1 - SLO Target) × Total Requests in Window
```

**Example**: For 99.9% availability SLO over 30 days with 10M requests:
- Error Budget = (1 - 0.999) × 10,000,000 = 10,000 failed requests
- Remaining Budget = Error Budget - Actual Errors

### Error Budget Consumption Stages

| Stage | Budget Consumed | Action |
|-------|-----------------|--------|
| **Green** | 0-50% | Normal operations, proceed with deployments |
| **Yellow** | 50-75% | Caution - review recent changes, slow rollouts |
| **Orange** | 75-90% | Warning - halt non-critical deployments, focus on reliability |
| **Red** | 90-100% | Critical - freeze all deployments, incident response mode |
| **Exceeded** | > 100% | Emergency - rollback recent changes, all hands on deck |

### Policy Enforcement

1. **Green**: Full velocity development, daily deployments allowed
2. **Yellow**: Require approval for high-risk changes, extended canary periods
3. **Orange**: Only critical bug fixes and security patches deployed
4. **Red**: Deployment freeze except for fixes to improve reliability
5. **Exceeded**: Mandatory postmortem, SLO review, process improvements

---

## SLO Review Process

### Monthly Review
- Check SLO attainment for each objective
- Analyze error budget consumption trends
- Identify top error contributors
- Update alert thresholds if needed

### Quarterly Review
- Reassess SLO targets based on user feedback
- Add/remove/modify SLOs as product evolves
- Review historical data for seasonality
- Update error budget policy if needed

### Annual Review
- Comprehensive SLO framework review
- Align with business objectives
- Benchmark against industry standards
- Update SLO classes and targets

---

## Dashboards

### SLO Overview Dashboard
**URL**: http://grafana:3000/d/slo-overview

Displays:
- Current SLO attainment (%) for all objectives
- Error budget remaining (%) for each SLO
- Trend charts (30-day rolling window)
- Alert status for each SLO

### API Performance Dashboard
**URL**: http://grafana:3000/d/api-performance

Displays:
- Request rate by endpoint
- Latency percentiles (p50, p95, p99)
- Error rates by status code
- Geographic distribution

### Agent Operations Dashboard
**URL**: http://grafana:3000/d/agent-ops

Displays:
- Agent run success rate
- Run duration percentiles
- Active runs and queue depth
- Error breakdown by type

---

## Runbooks

| Alert | Runbook URL |
|-------|-------------|
| ApiHighErrorRate | https://docs.example.com/runbooks/api-high-error-rate |
| ApiHighLatency | https://docs.example.com/runbooks/api-high-latency |
| AgentRunFailureRate | https://docs.example.com/runbooks/agent-high-failure-rate |
| LlmHighErrorRate | https://docs.example.com/runbooks/llm-high-error-rate |
| ToolHighFailureRate | https://docs.example.com/runbooks/tool-high-failure-rate |

---

## Appendix: Grafana Query Examples

### API Availability (30-day)
```promql
100 - (
  sum(rate(http_requests_total{status=~"5.."}[30d]))
  /
  sum(rate(http_requests_total[30d]))
) * 100
```

### Error Budget Remaining
```promql
1 - (
  sum(increase(http_requests_total{status=~"5.."}[30d]))
  /
  (sum(increase(http_requests_total[30d])) * (1 - 0.999))
)
```

### Agent Success Rate (7-day)
```promql
(
  sum(rate(agent_runs_total{status="success"}[7d]))
  /
  sum(rate(agent_runs_total[7d]))
) * 100
```

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-10-27 | Platform Team | Initial SLO definitions |

---

**Next Review**: January 27, 2026
