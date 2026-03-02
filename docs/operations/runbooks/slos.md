# Service Level Objectives (SLOs)

**Last Updated**: October 26, 2025  
**Review Period**: Monthly  
**Version**: 1.0.0

---

## Overview

This document defines Service Level Objectives (SLOs) for the Cineca Agentic Platform MCP tools. SLOs represent target performance and reliability metrics that the system aims to achieve.

### SLO Framework

- **SLI** (Service Level Indicator): Measurable metric (e.g., latency, error rate)
- **SLO** (Service Level Objective): Target value for SLI (e.g., p95 < 500ms)
- **SLA** (Service Level Agreement): Contractual commitment (if applicable)

---

## Performance SLOs

### Latency Targets by Tool Class

| Tool Class | p50 Latency | p95 Latency | p99 Latency | Notes |
|------------|-------------|-------------|-------------|-------|
| **Graph Query** | < 100ms | < 500ms | < 1000ms | Cached queries faster |
| **Graph Generate** | < 800ms | < 2000ms | < 5000ms | LLM-dependent |
| **System Tools** | < 50ms | < 200ms | < 500ms | Local operations |
| **Model Tools** | < 1000ms | < 3000ms | < 10000ms | External API calls |
| **User/Session** | < 75ms | < 300ms | < 750ms | Redis-backed |
| **Output/Viz** | < 100ms | < 400ms | < 1000ms | Data size dependent |

### Measurement Windows

- **p50 (median)**: 50th percentile latency
- **p95**: 95th percentile latency (accounts for outliers)
- **p99**: 99th percentile latency (worst-case scenarios)

---

## Reliability SLOs

### Availability Targets

| Component | Target Uptime | Max Downtime/Month | Max Downtime/Year |
|-----------|---------------|---------------------|-------------------|
| API Gateway | 99.9% | 43 minutes | 8.76 hours |
| Graph Tools | 99.5% | 3.6 hours | 43.8 hours |
| Model Tools | 99.0% | 7.2 hours | 87.6 hours |
| Storage (Postgres/Redis) | 99.95% | 22 minutes | 4.38 hours |

### Error Rate Targets

| Tool Class | Max Error Rate | Measurement |
|------------|----------------|-------------|
| Graph Query | < 1% | Errors / Total Requests |
| Graph Generate | < 5% | Failed generations (confidence < 0.5) |
| System Tools | < 0.5% | Errors / Total Requests |
| Model Tools | < 3% | API errors / Total Calls |
| User/Session | < 0.5% | Errors / Total Requests |
| Output/Viz | < 1% | Rendering failures / Total Requests |

---

## Detailed SLOs by Tool

### Graph Tools

#### graph.query

**Latency SLOs**:
- **p50**: < 100ms (simple queries with indexes)
- **p95**: < 500ms (complex queries)
- **p99**: < 1000ms (aggregations, multi-hop traversals)

**Performance Breakdown**:
```
Baseline (indexed single-node lookup):      ~10-20ms
Simple relationship traversal (1-2 hops):   ~50-100ms
Complex aggregation (WITH, GROUP BY):       ~200-500ms
Large result sets (>1000 rows):             ~400-800ms
```

**Cache Hit Targets**:
- Identical queries (same Cypher, same params): > 80% cache hit rate
- Cache latency: < 5ms (Redis lookup)

**Monitoring Query**:
```sql
SELECT
  percentile_cont(0.5) WITHIN GROUP (ORDER BY execution_time_ms) AS p50,
  percentile_cont(0.95) WITHIN GROUP (ORDER BY execution_time_ms) AS p95,
  percentile_cont(0.99) WITHIN GROUP (ORDER BY execution_time_ms) AS p99,
  COUNT(*) as total_queries
FROM query_metrics
WHERE tool_name = 'graph.query'
  AND timestamp > NOW() - INTERVAL '1 hour';
```

---

#### graph.generate_cypher

**Latency SLOs**:
- **p50**: < 800ms (simple NL queries)
- **p95**: < 2000ms (complex NL queries with schema context)
- **p99**: < 5000ms (very complex queries requiring multiple iterations)

**Performance Breakdown**:
```
LLM API call (GPT-4):                       ~500-1500ms
Schema analysis:                            ~50-100ms
Validation:                                 ~20-50ms
Total (typical):                            ~600-1700ms
```

**Quality SLOs**:
- **Confidence > 0.8**: > 70% of generations
- **Syntax validity**: > 95% of generated queries
- **Semantic accuracy**: > 80% (requires manual validation)

---

#### graph.secure_query

**Latency SLOs**:
- **p50**: < 900ms (NL→Cypher + Execute)
- **p95**: < 2500ms (includes safety validation)
- **p99**: < 6000ms (complex queries with multiple safety checks)

**Composed Latency**:
```
graph.generate_cypher:      ~800ms (p50)
Safety validation:          ~50ms
graph.query execution:      ~100ms
Total:                      ~950ms
```

**Safety SLOs**:
- **Mutation detection accuracy**: > 99% (block CREATE/DELETE/SET)
- **Expensive op detection**: > 90% (Cartesian products, large scans)
- **False positive rate**: < 5% (incorrectly blocked safe queries)

---

### System Tools

#### system.health

**Latency SLOs**:
- **p50**: < 20ms (cached component status)
- **p95**: < 100ms (fresh component checks)
- **p99**: < 200ms (all components checked)

**Component Check Latency**:
```
PostgreSQL ping:            ~5-10ms
Redis ping:                 ~2-5ms
Memgraph ping:              ~5-15ms
Total (all components):     ~15-30ms
```

**Reliability SLO**:
- Health endpoint availability: > 99.99% (critical for monitoring)

---

#### system.config

**Latency SLOs**:
- **p50**: < 10ms (config retrieval from memory)
- **p95**: < 50ms (config reload)
- **p99**: < 100ms (config validation)

---

### Model Tools

#### model.manage

**Latency SLOs**:
- **p50**: < 500ms (register/activate/deactivate)
- **p95**: < 2000ms (includes external API validation)
- **p99**: < 5000ms (network delays, retries)

**Operation Breakdown**:
```
Register provider:          ~300-800ms (API validation)
Activate instance:          ~100-300ms (local operation)
Deactivate instance:        ~50-150ms (soft delete)
List providers:             ~20-100ms (database query)
```

---

#### model.test

**Latency SLOs**:
- **p50**: < 1000ms (basic test suite, 5 tests)
- **p95**: < 3000ms (comprehensive test suite, 20 tests)
- **p99**: < 10000ms (slow models, network issues)

**Test Suite Composition**:
```
Ping test:                  ~100-300ms
Completion test (10 tokens): ~200-500ms
Completion test (100 tokens): ~500-1500ms
Error handling test:        ~100-200ms
Total (5 tests):            ~1000-2500ms
```

---

### User & Session Tools

#### session.manage

**Latency SLOs**:
- **p50**: < 50ms (Redis operations)
- **p95**: < 200ms (batch operations)
- **p99**: < 500ms (large pagination)

**Operation Breakdown**:
```
Create session:             ~10-30ms (Redis SET)
Get session:                ~5-15ms (Redis GET)
Update session:             ~10-25ms (Redis UPDATE)
Delete session:             ~5-15ms (Redis DEL)
List sessions (page=20):    ~50-150ms (Redis SCAN)
```

**TTL Enforcement SLO**:
- Session cleanup latency: < 60s (background job)
- Expired session detection: > 99% accuracy

---

#### cache.manage

**Latency SLOs**:
- **p50**: < 15ms (single key operations)
- **p95**: < 100ms (pattern invalidation)
- **p99**: < 300ms (large pattern matches)

**Operation Breakdown**:
```
GET:                        ~2-5ms
SET:                        ~3-8ms
DELETE:                     ~3-8ms
SCAN (pattern):             ~50-200ms (size-dependent)
```

---

### Output & Visualization Tools

#### output.format

**Latency SLOs**:
- **p50**: < 50ms (1000 rows)
- **p95**: < 200ms (10,000 rows)
- **p99**: < 500ms (100,000 rows)

**Format-Specific Latency**:
```
JSON (1000 rows):           ~10-30ms
CSV (1000 rows):            ~15-40ms
Markdown (1000 rows):       ~20-60ms
NDJSON (1000 rows):         ~12-35ms
```

**Throughput SLO**:
- Rows formatted per second: > 50,000 rows/s (JSON)

---

#### output.summarize

**Latency SLOs**:
- **p50**: < 500ms (extractive, 1000 words)
- **p95**: < 2000ms (abstractive with LLM, 5000 words)
- **p99**: < 10000ms (map-reduce, 50,000 words)

**Method-Specific Latency**:
```
Extractive (1000 words):    ~100-300ms
Abstractive (1000 words):   ~800-1500ms (LLM)
Map-reduce (10k words):     ~3000-6000ms (chunked)
Keywords (1000 words):      ~50-150ms
```

---

#### viz.render

**Latency SLOs**:
- **p50**: < 75ms (50 nodes, 100 edges)
- **p95**: < 250ms (100 nodes, 200 edges)
- **p99**: < 600ms (max size with validation)

**Rendering Breakdown**:
```
Mermaid (50 nodes):         ~30-80ms
DOT (50 nodes):             ~40-100ms
Table (1000 rows):          ~50-150ms
Sparkline (100 values):     ~10-30ms
```

---

## Capacity SLOs

### Throughput Targets

| Tool Class | Target RPS | Max RPS | Notes |
|------------|------------|---------|-------|
| Graph Query | 100 | 500 | With caching |
| Graph Generate | 10 | 50 | LLM rate limits apply |
| System Tools | 50 | 200 | Lightweight operations |
| Model Tools | 5 | 20 | External API dependent |
| User/Session | 200 | 1000 | Redis-backed |
| Output/Viz | 100 | 500 | CPU-bound |

### Resource Utilization Targets

| Resource | Target Usage | Warning Threshold | Critical Threshold |
|----------|--------------|-------------------|-------------------|
| CPU | < 60% | 75% | 90% |
| Memory | < 70% | 80% | 90% |
| Disk I/O | < 50% | 70% | 85% |
| Network | < 40% | 60% | 80% |

---

## Data Volume SLOs

### Maximum Supported Sizes

| Tool | Max Input Size | Max Output Size | Timeout |
|------|---------------|-----------------|---------|
| graph.query | 10MB (cypher) | 100MB (results) | 60s |
| graph.generate_cypher | 5KB (NL query) | 50KB (cypher) | 30s |
| output.format | 100MB (data) | 500MB (formatted) | 300s |
| output.summarize | 500KB (text) | 50KB (summary) | 120s |
| viz.render | 100 nodes, 200 edges | 1MB (SVG/Mermaid) | 10s |

---

## Quality SLOs

### Data Integrity

- **Backup success rate**: > 99% (daily backups)
- **Restore success rate**: > 99.5% (tested monthly)
- **Data loss**: 0 (RPO = 0, RTO < 4 hours)

### Correctness

- **Query result accuracy**: > 99.9% (compared to ground truth)
- **Cypher generation accuracy**: > 80% (semantic correctness)
- **Safety validation accuracy**: > 99% (mutation/expensive op detection)

---

## Monitoring & Alerting

### SLO Monitoring Queries

#### Check Graph Query p95 Latency

```sql
SELECT
  DATE_TRUNC('hour', timestamp) AS hour,
  percentile_cont(0.95) WITHIN GROUP (ORDER BY execution_time_ms) AS p95_latency
FROM query_metrics
WHERE tool_name = 'graph.query'
  AND timestamp > NOW() - INTERVAL '24 hours'
GROUP BY hour
ORDER BY hour DESC;
```

#### Check Error Rates

```sql
SELECT
  tool_name,
  COUNT(*) FILTER (WHERE status = 'error') * 100.0 / COUNT(*) AS error_rate_pct,
  COUNT(*) AS total_requests
FROM tool_invocations
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY tool_name
ORDER BY error_rate_pct DESC;
```

#### Check Availability

```sql
SELECT
  DATE_TRUNC('day', timestamp) AS day,
  COUNT(*) FILTER (WHERE status = 'up') * 100.0 / COUNT(*) AS uptime_pct
FROM health_checks
WHERE timestamp > NOW() - INTERVAL '30 days'
GROUP BY day
ORDER BY day DESC;
```

---

## SLO Compliance Reporting

### Monthly SLO Report Template

```markdown
# SLO Compliance Report - [Month Year]

## Executive Summary
- Overall SLO compliance: XX%
- Critical SLO violations: X
- Improvement actions: X

## Latency SLOs
| Tool Class | p95 Target | p95 Actual | Status |
|------------|------------|------------|--------|
| Graph Query | < 500ms | XXX ms | ✅/❌ |
| ...

## Error Rate SLOs
| Tool Class | Target | Actual | Status |
|------------|--------|--------|--------|
| Graph Query | < 1% | X.X% | ✅/❌ |
| ...

## Availability SLOs
| Component | Target | Actual Uptime | Downtime |
|-----------|--------|---------------|----------|
| API Gateway | 99.9% | XX.XX% | XX min |
| ...

## Action Items
1. [Action] - [Owner] - [Due Date]
2. ...
```

---

## SLO Budget

### Error Budget Calculation

**Formula**: Error Budget = (1 - SLO) × Total Requests

**Example** (Graph Query):
- SLO: 99.5% success rate
- Error budget: 0.5% of requests
- If 1M requests/month → 5,000 allowed errors/month

**Budget Tracking**:
```sql
SELECT
  tool_name,
  (1 - target_slo) * SUM(total_requests) AS error_budget,
  SUM(total_errors) AS errors_consumed,
  ((1 - target_slo) * SUM(total_requests) - SUM(total_errors)) AS budget_remaining
FROM monthly_metrics
WHERE month = DATE_TRUNC('month', CURRENT_DATE)
GROUP BY tool_name;
```

---

## Continuous Improvement

### SLO Review Cycle

1. **Weekly**: Review latency trends, identify regressions
2. **Monthly**: Generate SLO compliance report
3. **Quarterly**: Adjust SLO targets based on capacity and user needs
4. **Annually**: Major SLO framework review

### Performance Optimization Triggers

- **p95 latency > target**: Investigate slow queries, optimize indexes
- **Error rate > budget**: Review error patterns, improve handling
- **Availability < target**: Improve failover, add redundancy

---

**See Also**:
- [Troubleshooting Guide](./troubleshooting-tools.md) - Diagnostic procedures
- [Alerts](./alerts.md) - Alert definitions and thresholds
- [Architecture](../../architecture.md) - System design
