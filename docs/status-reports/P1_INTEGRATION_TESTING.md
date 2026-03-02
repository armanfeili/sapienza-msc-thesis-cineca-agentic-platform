# P1 Integration Testing Guide

**Status**: Ready for Integration Testing  
**Docker**: ✅ Running (all services healthy)  
**Tests**: ✅ 123/123 passing (unit tests)  
**Auth**: ✅ Token fetch script available

---

## 🎯 Goal

Validate P1 hardened tools work end-to-end with:
- Real Docker environment (Memgraph, PostgreSQL, Redis, API)
- Real Auth0 authentication
- Real RBAC enforcement
- Real audit trail logging

---

## 🚀 Quick Start

### 1. Fetch Fresh Auth Tokens

```bash
cd /Users/armanfeili/Arman/Sapienza\ Courses/4-semester/Thesis/ILP-Thesis-2025/Cineca-Agentic-Platform

# Fetch tokens from Auth0
python fetch_tokens.py

# Load tokens into environment
source /tmp/tokens.sh

# Verify tokens loaded
echo "Admin: ${ADMIN_TOKEN:0:20}..."
echo "User: ${USER_TOKEN:0:20}..."
echo "Machine: ${MACHINE_TOKEN:0:20}..."
```

**Expected Output**:
```
Fetching ADMIN token...
✓ ADMIN token: eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6...
Fetching USER token...
✓ USER token: eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6...
Fetching MACHINE token...
✓ MACHINE token: eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6...

✅ All tokens fetched and saved to /tmp/tokens.sh
✅ Tokens also saved to /tmp/tokens.json
```

### 2. Verify Docker Services

```bash
docker compose ps
```

**Expected Services** (all should be "Up" and healthy):
- ✅ app (API server on :8000)
- ✅ memgraph (graph DB on :7687)
- ✅ postgres (control DB on :5432)
- ✅ redis (cache on :6379)
- ✅ ollama (LLM on :11434)

### 3. Test API Connectivity

```bash
curl -s http://localhost:8000/health | jq .
```

**Expected**:
```json
{
  "status": "healthy",
  "services": {
    "api": "ok",
    "memgraph": "ok",
    "postgres": "ok",
    "redis": "ok"
  }
}
```

---

## 🧪 P1 Tool Integration Tests

### Test 1: graph.query (Execute Raw Cypher)

#### Test 1.1: Run Query (User Token - Basic Scope)

```bash
curl -X POST http://localhost:8000/api/v2/mcp/tools/invoke \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "graph.query",
    "payload": {
      "action": "run",
      "cypher": "MATCH (n) RETURN labels(n) AS labels LIMIT 5",
      "read_only": true
    }
  }' | jq .
```

**Expected**:
```json
{
  "ok": true,
  "action": "run",
  "columns": ["labels"],
  "rows": [
    {"labels": ["User"]},
    {"labels": ["Task"]},
    ...
  ],
  "rowcount": 5
}
```

#### Test 1.2: Explain Query (User Token)

```bash
curl -X POST http://localhost:8000/api/v2/mcp/tools/invoke \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "graph.query",
    "payload": {
      "action": "explain",
      "cypher": "MATCH (u:User)-[:ASSIGNED_TO]->(t:Task) RETURN u.name, t.title"
    }
  }' | jq .
```

**Expected**: Execution plan returned

#### Test 1.3: Write Detection (User Token - Read-Only)

```bash
curl -X POST http://localhost:8000/api/v2/mcp/tools/invoke \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "graph.query",
    "payload": {
      "action": "run",
      "cypher": "CREATE (n:User {name: \"Hacker\"}) RETURN n",
      "read_only": true
    }
  }' | jq .
```

**Expected**: Error - write operation blocked
```json
{
  "ok": false,
  "error": "Write operation not allowed in read-only mode"
}
```

---

### Test 2: graph.generate_cypher (SQL-like Abstraction)

#### Test 2.1: Select Action (User Token)

```bash
curl -X POST http://localhost:8000/api/v2/mcp/tools/invoke \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "graph.generate_cypher",
    "payload": {
      "action": "select",
      "labels": ["User"],
      "where": {"active": true},
      "return_fields": ["name", "email"],
      "limit": 10
    }
  }' | jq .
```

**Expected**:
```json
{
  "ok": true,
  "action": "select",
  "cypher": "MATCH (n:User) WHERE n.active = $active RETURN n.name, n.email LIMIT 10",
  "params": {"active": true},
  "is_write": false
}
```

#### Test 2.2: Count by Label (User Token)

```bash
curl -X POST http://localhost:8000/api/v2/mcp/tools/invoke \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "graph.generate_cypher",
    "payload": {
      "action": "count_by_label"
    }
  }' | jq .
```

**Expected**:
```json
{
  "ok": true,
  "action": "count_by_label",
  "cypher": "MATCH (n) RETURN labels(n)[0] AS label, COUNT(n) AS count ORDER BY count DESC",
  "is_write": false
}
```

---

### Test 3: graph.secure_query (NL → Cypher → Results)

#### Test 3.1: Ask Action (User Token)

```bash
curl -X POST http://localhost:8000/api/v2/mcp/tools/invoke \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "graph.secure_query",
    "payload": {
      "action": "ask",
      "prompt": "Show me all users with their email addresses",
      "format": "json",
      "max_rows": 5
    }
  }' | jq .
```

**Expected**:
```json
{
  "ok": true,
  "action": "ask",
  "prompt": "Show me all users with their email addresses",
  "generated_cypher": "MATCH (u:User) RETURN u.name, u.email LIMIT 5",
  "format": "json",
  "results": [
    {"u.name": "Alice", "u.email": "alice@example.com"},
    ...
  ]
}
```

#### Test 3.2: Validate Action (User Token)

```bash
curl -X POST http://localhost:8000/api/v2/mcp/tools/invoke \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "graph.secure_query",
    "payload": {
      "action": "validate",
      "cypher": "MATCH (u:User) RETURN u.name"
    }
  }' | jq .
```

**Expected**:
```json
{
  "ok": true,
  "action": "validate",
  "cypher": "MATCH (u:User) RETURN u.name",
  "is_safe": true,
  "is_write": false
}
```

#### Test 3.3: Validate Blocks Writes (User Token)

```bash
curl -X POST http://localhost:8000/api/v2/mcp/tools/invoke \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "graph.secure_query",
    "payload": {
      "action": "validate",
      "cypher": "CREATE (n:User {name: \"Hacker\"}) RETURN n"
    }
  }' | jq .
```

**Expected**:
```json
{
  "ok": false,
  "error": "Write operations are not allowed (found: CREATE)"
}
```

---

### Test 4: security.permissions (RBAC Checking)

#### Test 4.1: Check Permission (User Token)

```bash
curl -X POST http://localhost:8000/api/v2/mcp/tools/invoke \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "security.permissions",
    "payload": {
      "action": "check",
      "resource": "mcp.tools.graph.query",
      "op": "invoke",
      "context": {
        "tenant": "test-tenant",
        "roles": ["user"]
      }
    }
  }' | jq .
```

**Expected**:
```json
{
  "ok": true,
  "action": "check",
  "allowed": true,
  "resource": "mcp.tools.graph.query",
  "op": "invoke"
}
```

#### Test 4.2: List Roles (User Token)

```bash
curl -X POST http://localhost:8000/api/v2/mcp/tools/invoke \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "security.permissions",
    "payload": {
      "action": "list_roles"
    }
  }' | jq .
```

**Expected**:
```json
{
  "ok": true,
  "action": "list_roles",
  "roles": [
    {
      "name": "admin",
      "description": "Full access to all resources",
      "rule_count": 5
    },
    {
      "name": "user",
      "description": "Basic access to tools",
      "rule_count": 3
    },
    ...
  ]
}
```

#### Test 4.3: Resolve Permissions (User Token)

```bash
curl -X POST http://localhost:8000/api/v2/mcp/tools/invoke \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "security.permissions",
    "payload": {
      "action": "resolve",
      "context": {
        "tenant": "test-tenant",
        "roles": ["user", "analyst"]
      }
    }
  }' | jq .
```

**Expected**:
```json
{
  "ok": true,
  "action": "resolve",
  "summary": {
    "total_rules": 15,
    "allow_rules": 12,
    "deny_rules": 3
  },
  "details": [...]
}
```

---

### Test 5: graph.schema (Schema Discovery)

#### Test 5.1: List Labels (User Token)

```bash
curl -X POST http://localhost:8000/api/v2/mcp/tools/invoke \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "graph.schema",
    "payload": {
      "action": "labels"
    }
  }' | jq .
```

**Expected**:
```json
{
  "ok": true,
  "action": "labels",
  "items": ["User", "Task", "Project", "Agent"]
}
```

#### Test 5.2: Node Properties (User Token)

```bash
curl -X POST http://localhost:8000/api/v2/mcp/tools/invoke \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "graph.schema",
    "payload": {
      "action": "node_properties",
      "label": "User"
    }
  }' | jq .
```

**Expected**:
```json
{
  "ok": true,
  "action": "node_properties",
  "label": "User",
  "items": ["name", "email", "created_at", "active"]
}
```

#### Test 5.3: Node Counts (User Token)

```bash
curl -X POST http://localhost:8000/api/v2/mcp/tools/invoke \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "graph.schema",
    "payload": {
      "action": "node_counts"
    }
  }' | jq .
```

**Expected**:
```json
{
  "ok": true,
  "action": "node_counts",
  "items": [
    {"label": "User", "count": 150},
    {"label": "Task", "count": 320},
    {"label": "Project", "count": 45}
  ]
}
```

#### Test 5.4: Inventory (User Token)

```bash
curl -X POST http://localhost:8000/api/v2/mcp/tools/invoke \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "graph.schema",
    "payload": {
      "action": "inventory"
    }
  }' | jq .
```

**Expected**: Comprehensive schema summary (columns + rows)

---

## 🔒 RBAC Tests

### Test 6: Admin-Only Access (Admin Token)

```bash
curl -X POST http://localhost:8000/api/v2/mcp/tools/invoke \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "admin.processes",
    "payload": {
      "action": "list"
    }
  }' | jq .
```

**Expected**: Success (admin has admin:all scope)

### Test 7: Admin Blocked for User (User Token)

```bash
curl -X POST http://localhost:8000/api/v2/mcp/tools/invoke \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "admin.processes",
    "payload": {
      "action": "list"
    }
  }' | jq .
```

**Expected**: Error (user lacks admin:all scope)
```json
{
  "ok": false,
  "error": "Insufficient permissions: requires scope 'admin:all'"
}
```

### Test 8: Machine Token (Internal Scope)

```bash
curl -X POST http://localhost:8000/api/v2/mcp/tools/invoke \
  -H "Authorization: Bearer $MACHINE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "graph.query",
    "payload": {
      "action": "run",
      "cypher": "MATCH (n) RETURN COUNT(n) AS total"
    }
  }' | jq .
```

**Expected**: Success (machine has internal:all scope)

---

## 📊 Audit Trail Verification

### Check Audit Logs

```bash
# View recent audit logs
docker compose logs app --tail=100 | grep "AUDIT"
```

**Expected Output**:
```
[AUDIT] principal=auth0|user123 tenant=test-tenant tool=graph.query action=run duration=45ms status=success
[AUDIT] principal=auth0|user123 tenant=test-tenant tool=graph.secure_query action=ask duration=1200ms status=success
[AUDIT] principal=auth0|user123 tenant=test-tenant tool=security.permissions action=check duration=12ms status=success
```

### Check Metrics

```bash
# Query Prometheus metrics
curl -s http://localhost:9090/api/v1/query?query=mcp_tool_invocations_total | jq .
```

**Expected**: Counter metrics for tool invocations

---

## ✅ Success Criteria

All tests should:
- ✅ Return `"ok": true` for valid requests
- ✅ Enforce RBAC (admin-only blocked for user token)
- ✅ Block write operations (graph.secure_query.validate)
- ✅ Log audit trail (AUDIT entries in logs)
- ✅ Collect metrics (Prometheus counters incremented)
- ✅ Return expected data structures (columns, rows, items)

---

## 🐛 Troubleshooting

### Issue: "Unauthorized" Error

**Symptom**:
```json
{"detail": "Unauthorized"}
```

**Solution**:
```bash
# Tokens expire after 1 hour - fetch fresh ones
python fetch_tokens.py
source /tmp/tokens.sh
```

### Issue: Service Unhealthy

**Symptom**:
```
app    Up 5 minutes (unhealthy)
```

**Solution**:
```bash
# Check service logs
docker compose logs app --tail=50

# Restart service
docker compose restart app
```

### Issue: Connection Refused

**Symptom**:
```
curl: (7) Failed to connect to localhost port 8000
```

**Solution**:
```bash
# Verify Docker is running
docker compose ps

# Restart all services
docker compose down
docker compose up -d --build
```

---

## 📝 Integration Test Results Template

```markdown
# P1 Integration Test Results

**Date**: YYYY-MM-DD  
**Tester**: [Your Name]  
**Environment**: Docker (local)

## Test Summary

| Test | Tool | Action | Status | Notes |
|------|------|--------|--------|-------|
| 1.1 | graph.query | run | ✅ | Returned 5 rows |
| 1.2 | graph.query | explain | ✅ | Execution plan OK |
| 1.3 | graph.query | run (write blocked) | ✅ | Error as expected |
| 2.1 | graph.generate_cypher | select | ✅ | Cypher generated |
| 2.2 | graph.generate_cypher | count_by_label | ✅ | Counts returned |
| 3.1 | graph.secure_query | ask | ✅ | NL→Cypher→Results |
| 3.2 | graph.secure_query | validate | ✅ | Read-only approved |
| 3.3 | graph.secure_query | validate (write) | ✅ | Write blocked |
| 4.1 | security.permissions | check | ✅ | Permission allowed |
| 4.2 | security.permissions | list_roles | ✅ | 3 roles returned |
| 4.3 | security.permissions | resolve | ✅ | Summary + details |
| 5.1 | graph.schema | labels | ✅ | 4 labels returned |
| 5.2 | graph.schema | node_properties | ✅ | User properties OK |
| 5.3 | graph.schema | node_counts | ✅ | Counts per label |
| 5.4 | graph.schema | inventory | ✅ | Full schema OK |
| 6 | admin.processes | list (admin) | ✅ | Admin access OK |
| 7 | admin.processes | list (user) | ✅ | Blocked as expected |
| 8 | graph.query | run (machine) | ✅ | Machine token OK |

## RBAC Results

- ✅ Admin token: admin:all scope enforced
- ✅ User token: tools:invoke:basic scope enforced
- ✅ Machine token: internal:all scope enforced
- ✅ Write blocking: graph.secure_query blocks CREATE/MERGE/DELETE/SET

## Audit Trail

- ✅ All invocations logged
- ✅ Principal + tenant + tool + action captured
- ✅ Duration tracked
- ✅ Status (success/error) logged

## Metrics

- ✅ mcp_tool_invocations_total counter incremented
- ✅ mcp_tool_duration_seconds histogram updated
- ✅ mcp_tool_errors_total counter for blocked writes

## Overall Status

**✅ PASS** - All P1 tools working end-to-end with RBAC, audit, and metrics.
```

---

**Integration Testing Guide: READY**  
*Proceed with manual testing using curl commands above*
