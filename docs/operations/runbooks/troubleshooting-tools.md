# MCP Tools Troubleshooting Guide

**Last Updated**: October 26, 2025  
**Version**: 1.0.0

---

## Overview

This guide provides troubleshooting procedures for MCP tools organized by category. Use this document to diagnose and resolve common issues with tool invocations, performance problems, and error conditions.

---

## Table of Contents

- [Graph Tools](#graph-tools)
- [System Tools](#system-tools)
- [Model Tools](#model-tools)
- [User & Session Tools](#user--session-tools)
- [Output & Visualization Tools](#output--visualization-tools)
- [Common Issues](#common-issues)
- [Diagnostic Commands](#diagnostic-commands)

---

## Graph Tools

### graph.query

#### Issue: Query Timeout

**Symptoms**:
- 504 Gateway Timeout
- `TIMEOUT` error code
- Query execution > 30s

**Diagnosis**:
```bash
# Check query execution time
docker compose logs app | grep "graph.query" | grep "execution_time"

# Check Memgraph slow queries
docker compose exec memgraph mgconsole -e "SHOW QUERY STATS;"
```

**Solutions**:
1. **Optimize Query**:
   ```cypher
   # Add index
   CREATE INDEX ON :Person(email);
   
   # Use LIMIT
   MATCH (p:Person) RETURN p LIMIT 100;
   
   # Add WHERE clause
   MATCH (p:Person) WHERE p.age > 30 RETURN p;
   ```

2. **Increase Timeout**:
   ```python
   payload = {
       "action": "execute",
       "cypher": "...",
       "timeout": 120  # Increase to 2 minutes
   }
   ```

3. **Break into Smaller Queries**:
   ```python
   # Instead of one large query
   # Split into batch processing
   for batch in range(0, total, 1000):
       query = f"MATCH (p:Person) SKIP {batch} LIMIT 1000 RETURN p"
   ```

#### Issue: Cartesian Product / Expensive Operation

**Symptoms**:
- Very slow query execution
- High CPU usage
- Memory warnings

**Diagnosis**:
```cypher
# Check query plan
EXPLAIN MATCH (p:Person), (c:Company) RETURN p, c;
# Look for "CartesianProduct" in plan
```

**Solutions**:
```cypher
# ❌ BAD: Cartesian product
MATCH (p:Person), (c:Company) RETURN p, c

# ✅ GOOD: Use relationship
MATCH (p:Person)-[:WORKS_AT]->(c:Company) RETURN p, c
```

---

### graph.generate_cypher

#### Issue: Low Confidence Score

**Symptoms**:
- `confidence < 0.7`
- Generated Cypher doesn't match intent
- Syntax errors in generated query

**Diagnosis**:
```python
result = invoke({
    "action": "generate",
    "nl_query": "Find people"
})

print(f"Confidence: {result['confidence']}")
print(f"Cypher: {result['cypher']}")
```

**Solutions**:
1. **Provide Schema Context**:
   ```python
   payload = {
       "action": "generate",
       "nl_query": "Find engineers at Acme Corp",
       "schema_context": "Person nodes have 'role' property, Company nodes have 'name' property, connected via WORKS_AT relationship"
   }
   ```

2. **Rephrase Query**:
   ```python
   # ❌ Vague
   "Find stuff"
   
   # ✅ Specific
   "Find all Person nodes where role equals 'Engineer' and they work at a Company named 'Acme Corp'"
   ```

3. **Validate Before Execution**:
   ```python
   payload = {"action": "generate", "nl_query": "...", "validate": True}
   result = invoke(payload)
   
   if result['confidence'] < 0.8:
       print("Low confidence, review generated Cypher:")
       print(result['cypher'])
   ```

---

### graph.secure_query

#### Issue: Query Blocked by Safety Validation

**Symptoms**:
- `safety_checks.approved = false`
- `mutation_detected = true` or `expensive_ops = true`

**Diagnosis**:
```python
result = invoke({
    "action": "secure_execute",
    "nl_query": "Delete all users"
})

print(result['safety_checks'])
# {
#   "mutation_detected": true,
#   "expensive_ops": false,
#   "approved": false
# }
```

**Solutions**:
1. **For Mutations**: Use explicit admin tools, not NL queries
   ```python
   # ❌ Don't use secure_query for mutations
   "Delete user Alice"
   
   # ✅ Use admin API endpoint
   DELETE /v1/admin/users/{user_id}
   ```

2. **For Expensive Operations**: Add filters
   ```python
   # ❌ Triggers expensive_ops flag
   "Show all people and all companies"
   
   # ✅ Add relationship constraint
   "Show people who work at companies"
   ```

---

## System Tools

### system.health

#### Issue: Component Reported as Unhealthy

**Symptoms**:
- `status: "unhealthy"`
- Specific component (postgres/redis/memgraph) down

**Diagnosis**:
```bash
# Check component health
curl http://localhost:8000/health | jq '.components'

# Check Docker containers
docker compose ps

# Check logs
docker compose logs postgres
docker compose logs redis
docker compose logs memgraph
```

**Solutions**:
1. **PostgreSQL Down**:
   ```bash
   # Restart PostgreSQL
   docker compose restart postgres
   
   # Check PostgreSQL logs
   docker compose logs postgres --tail=100
   
   # Verify connection
   docker compose exec postgres psql -U postgres -c "SELECT 1;"
   ```

2. **Redis Down**:
   ```bash
   # Restart Redis
   docker compose restart redis
   
   # Check Redis
   docker compose exec redis redis-cli PING
   ```

3. **Memgraph Down**:
   ```bash
   # Restart Memgraph
   docker compose restart memgraph
   
   # Check Memgraph
   docker compose exec memgraph mgconsole -e "SHOW STORAGE INFO;"
   ```

---

### system.config

#### Issue: Unable to Retrieve Configuration

**Symptoms**:
- 403 Forbidden
- `UNAUTHORIZED` error

**Diagnosis**:
```bash
# Check token scopes
python -c "import jwt; import os; print(jwt.decode(os.getenv('ACCESS_TOKEN'), options={'verify_signature': False})['scope'])"
```

**Solutions**:
1. **Use Admin Token**:
   ```bash
   # system.config requires admin:all scope
   python scripts/generate_test_token.py --admin
   ```

2. **Check Required Scope**:
   ```python
   # Required scope: system:admin or admin:all
   headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
   ```

---

## Model Tools

### model.manage

#### Issue: Model Registration Failed

**Symptoms**:
- `INVALID_INPUT` error
- Provider connection failed

**Diagnosis**:
```bash
# Check provider configuration
curl -X POST http://localhost:8000/v1/tools/model.manage/invoke \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"action": "list_providers"}'
```

**Solutions**:
1. **Verify Provider Config**:
   ```python
   payload = {
       "action": "register",
       "provider_id": "openai",
       "config": {
           "api_key": "sk-...",  # Valid API key
           "base_url": "https://api.openai.com/v1",  # Correct URL
           "timeout": 30
       }
   }
   ```

2. **Test Connection**:
   ```bash
   # Test OpenAI API
   curl https://api.openai.com/v1/models \
     -H "Authorization: Bearer sk-..."
   ```

---

### model.test

#### Issue: Model Tests Failing

**Symptoms**:
- `tests_passed < tests_run`
- High latency (p95 > 1000ms)

**Diagnosis**:
```python
result = invoke({
    "action": "run_tests",
    "instance_id": "gpt-4-instance-1"
})

print(f"Passed: {result['tests_passed']}/{result['tests_run']}")
print(f"p95 latency: {result['latency_p95']}ms")
```

**Solutions**:
1. **Check Model Instance Status**:
   ```bash
   curl -X GET http://localhost:8000/v1/admin/models/instances/gpt-4-instance-1 \
     -H "Authorization: Bearer $ADMIN_TOKEN"
   ```

2. **Adjust Test Parameters**:
   ```python
   payload = {
       "action": "run_tests",
       "instance_id": "gpt-4-instance-1",
       "max_tokens": 50,  # Reduce for faster tests
       "timeout": 10  # Increase for slow models
   }
   ```

---

## User & Session Tools

### session.manage

#### Issue: Session Expired Prematurely

**Symptoms**:
- Session invalidated before TTL
- `SESSION_NOT_FOUND` error

**Diagnosis**:
```python
result = invoke({
    "action": "get",
    "session_id": "sess_123"
})

if result['status'] == 'error':
    print(f"Session error: {result['message']}")
```

**Solutions**:
1. **Check TTL Configuration**:
   ```python
   # Default TTL is 1 hour, max 24 hours
   payload = {
       "action": "create",
       "user_id": "user_123",
       "ttl_seconds": 7200  # 2 hours
   }
   ```

2. **Verify Redis**:
   ```bash
   # Check if session exists in Redis
   docker compose exec redis redis-cli GET "session:sess_123"
   
   # Check TTL
   docker compose exec redis redis-cli TTL "session:sess_123"
   ```

---

### cache.manage

#### Issue: Cache Invalidation Not Working

**Symptoms**:
- Stale data returned
- Pattern match not working

**Diagnosis**:
```bash
# Check Redis keys
docker compose exec redis redis-cli KEYS "user:*:profile"

# Check pattern matching
docker compose exec redis redis-cli SCAN 0 MATCH "user:*:profile"
```

**Solutions**:
1. **Use Correct Pattern Syntax**:
   ```python
   # Redis glob pattern syntax
   payload = {
       "action": "invalidate_pattern",
       "pattern": "user:*:profile"  # * matches any characters
   }
   ```

2. **Manual Invalidation**:
   ```bash
   # Delete specific keys
   docker compose exec redis redis-cli DEL "user:123:profile"
   
   # Delete by pattern
   docker compose exec redis redis-cli --scan --pattern "user:*:profile" | xargs docker compose exec redis redis-cli DEL
   ```

---

## Output & Visualization Tools

### output.format

#### Issue: Unicode Encoding Errors

**Symptoms**:
- `UnicodeEncodeError`
- Garbled characters in output

**Diagnosis**:
```python
result = invoke({
    "action": "json",
    "data": {"name": "Café ☕"}
})

print(result['content'])
```

**Solutions**:
1. **Use Unicode-Safe Formatting**:
   ```python
   # P7 tools default to ensure_ascii=False
   payload = {
       "action": "json",
       "data": data,
       # Unicode preserved by default
   }
   ```

2. **Check System Locale**:
   ```bash
   # Set UTF-8 locale
   export LANG=en_US.UTF-8
   export LC_ALL=en_US.UTF-8
   ```

---

### output.summarize

#### Issue: Poor Summary Quality

**Symptoms**:
- Summary too generic
- Key information missing

**Diagnosis**:
```python
result = invoke({
    "action": "abstractive",
    "text": long_text,
    "simulate": True
})

print(f"Summary length: {len(result['summary'])}")
print(f"Original length: {len(long_text)}")
```

**Solutions**:
1. **Adjust Ratio**:
   ```python
   payload = {
       "action": "extract",
       "text": text,
       "ratio": 0.2  # 20% of original (reduce for shorter summary)
   }
   ```

2. **Use Map-Reduce for Long Texts**:
   ```python
   payload = {
       "action": "map_reduce",
       "text": very_long_text,
       "chunk_chars": 2000,
       "overlap": 200
   }
   ```

---

### viz.render

#### Issue: Graph Rendering Failed

**Symptoms**:
- `INVALID_INPUT` error
- Missing required fields

**Diagnosis**:
```python
result = invoke({
    "action": "graph_mermaid",
    "nodes": [{}],  # Missing 'id'
    "edges": []
})

print(result['message'])
# "Each node must have an 'id', 'name', or 'label' field"
```

**Solutions**:
1. **Ensure Required Fields**:
   ```python
   # ✅ Valid nodes
   nodes = [
       {"id": "A", "label": "Node A"},
       {"id": "B", "label": "Node B"}
   ]
   
   # ✅ Valid edges
   edges = [
       {"from": "A", "to": "B", "label": "connects"}
   ]
   ```

2. **Check Size Limits**:
   ```python
   payload = {
       "action": "graph_mermaid",
       "nodes": nodes[:100],  # Limit to 100 nodes
       "edges": edges[:200],  # Limit to 200 edges
       "max_nodes": 100,
       "max_edges": 200
   }
   ```

---

## Common Issues

### Authentication Errors

#### 401 Unauthorized

**Diagnosis**:
```bash
# Check token
echo $ACCESS_TOKEN

# Decode token
python -c "import jwt; import os; print(jwt.decode(os.getenv('ACCESS_TOKEN'), options={'verify_signature': False}))"
```

**Solutions**:
```bash
# Regenerate token
python scripts/generate_test_token.py

# Verify token is set
export ACCESS_TOKEN=$(cat .env.tokens | grep ACCESS_TOKEN | cut -d= -f2)
```

#### 403 Forbidden (Insufficient Scope)

**Diagnosis**:
```bash
# Check token scopes
python -c "import jwt; import os; token = os.getenv('ACCESS_TOKEN'); print(jwt.decode(token, options={'verify_signature': False}).get('scope', 'No scopes'))"
```

**Solutions**:
```bash
# Generate admin token
python scripts/generate_test_token.py --admin

# Or request specific scopes
python scripts/generate_test_token.py --scopes "graph:query,graph:generate,user:profile"
```

---

### Rate Limiting

#### 429 Too Many Requests

**Diagnosis**:
```bash
# Check rate limit headers
curl -I http://localhost:8000/v1/tools/graph.query/invoke \
  -H "Authorization: Bearer $ACCESS_TOKEN"

# Look for:
# X-RateLimit-Limit: 100
# X-RateLimit-Remaining: 0
# X-RateLimit-Reset: 1698345600
```

**Solutions**:
```python
import time

def retry_with_backoff(func, max_retries=3):
    for i in range(max_retries):
        try:
            return func()
        except requests.HTTPError as e:
            if e.response.status_code == 429:
                wait = 2 ** i
                print(f"Rate limited. Waiting {wait}s...")
                time.sleep(wait)
            else:
                raise
```

---

## Diagnostic Commands

### Check System Status

```bash
# All services
docker compose ps

# App logs
docker compose logs app --tail=100 -f

# Database health
curl http://localhost:8000/health | jq '.components'
```

### Check Tool Status

```bash
# List available tools
curl http://localhost:8000/v1/tools \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq '.tools[] | .name'

# Check tool manifest
curl http://localhost:8000/v1/admin/tools/manifest \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.'
```

### Performance Metrics

```bash
# Query execution times
docker compose logs app | grep "execution_time_ms" | tail -20

# Slow queries (> 1s)
docker compose logs app | grep "execution_time_ms" | awk '$NF > 1000' | tail -10

# Error rate
docker compose logs app | grep -c "ERROR"

# Request count
docker compose logs app | grep "POST /v1/tools" | wc -l
```

### Database Diagnostics

```bash
# PostgreSQL
docker compose exec postgres psql -U postgres -d cineca -c "\dt"

# Redis
docker compose exec redis redis-cli INFO stats

# Memgraph
docker compose exec memgraph mgconsole -e "SHOW STORAGE INFO;"
```

---

## Escalation Path

1. **Check Logs**: `docker compose logs app --tail=200`
2. **Check Health**: `curl http://localhost:8000/health`
3. **Review Metrics**: See [slos.md](./slos.md) for performance baselines
4. **Check Alerts**: See [alerts.md](./alerts.md) for alert definitions
5. **Contact Support**: Provide:
   - Error message
   - Request payload
   - Logs (last 200 lines)
   - System health output

---

**See Also**:
- [SLOs](./slos.md) - Performance targets
- [Alerts](./alerts.md) - Alert definitions
- [MCP Tools Reference](../../mcp/TOOLS_REFERENCE.md) - Complete tool documentation
