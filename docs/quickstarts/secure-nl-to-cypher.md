# Quickstart: Secure Natural Language to Cypher Queries

**Difficulty**: Intermediate  
**Time**: 15 minutes  
**Prerequisites**: Python 3.11+, Docker, valid OAuth2 token

---

## Overview

This guide demonstrates how to safely convert natural language queries to Cypher using the **graph.secure_query** tool with built-in safety guardrails.

### What You'll Learn

- Convert natural language to Cypher queries securely
- Understand safety validation mechanisms
- Handle mutation detection and expensive operations
- Implement error handling and logging

---

## Setup

### 1. Start Services

```bash
# Start all required services
docker compose up -d

# Verify health
curl http://localhost:8000/health
```

### 2. Obtain Authentication Token

```bash
# Set your Auth0 credentials
export AUTH0_DOMAIN="your-domain.auth0.com"
export AUTH0_CLIENT_ID="your-client-id"
export AUTH0_CLIENT_SECRET="your-secret"
export AUTH0_AUDIENCE="https://api.cineca-platform.com"

# Get access token
python scripts/generate_test_token.py
```

### 3. Install Python Client (Optional)

```bash
pip install requests python-dotenv
```

---

## Basic Usage

### Example 1: Simple Query

**Natural Language**: "Find all people named Alice"

```python
import requests
import os

API_BASE = "http://localhost:8000/v1"
TOKEN = os.getenv("ACCESS_TOKEN")

# Headers with authentication
headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

# Payload
payload = {
    "action": "secure_execute",
    "nl_query": "Find all people named Alice",
    "max_results": 100
}

# Execute
response = requests.post(
    f"{API_BASE}/tools/graph.secure_query/invoke",
    headers=headers,
    json=payload
)

result = response.json()

# Check safety validation
if result["safety_checks"]["approved"]:
    print(f"✅ Query approved")
    print(f"Generated Cypher: {result['generated_cypher']}")
    print(f"Results: {result['count']} rows")
    for row in result["results"]:
        print(row)
else:
    print(f"❌ Query blocked: {result['safety_checks']}")
```

**Output**:
```
✅ Query approved
Generated Cypher: MATCH (p:Person {name: 'Alice'}) RETURN p LIMIT 100
Results: 3 rows
{'p': {'name': 'Alice', 'age': 30, 'email': 'alice@example.com'}}
{'p': {'name': 'Alice Smith', 'age': 25, 'email': 'asmith@example.com'}}
{'p': {'name': 'Alice Johnson', 'age': 35, 'email': 'ajohnson@example.com'}}
```

---

## Security Best Practices

### 1. Always Use `secure_query` for User Input

```python
# ✅ SAFE: Uses built-in safety validation
def handle_user_query(user_input: str):
    payload = {
        "action": "secure_execute",
        "nl_query": user_input,
        "max_results": 100
    }
    
    response = requests.post(
        f"{API_BASE}/tools/graph.secure_query/invoke",
        headers=headers,
        json=payload
    )
    
    result = response.json()
    
    # Safety checks are automatic
    if not result["safety_checks"]["approved"]:
        raise ValueError("Query blocked by safety validation")
    
    return result["results"]

# ❌ DANGEROUS: No safety validation
def unsafe_query(user_input: str):
    # Direct Cypher execution without validation
    payload = {
        "action": "execute",
        "cypher": f"MATCH (n) WHERE n.name = '{user_input}' RETURN n"
        # Risk: SQL injection equivalent, no mutation detection
    }
    return requests.post(f"{API_BASE}/tools/graph.query/invoke", ...)
```

### 2. Check Safety Flags

```python
result = response.json()

safety = result["safety_checks"]

# Check for mutations
if safety["mutation_detected"]:
    print("⚠️  Query attempts to modify data (CREATE/DELETE/SET)")
    # Log for audit, notify admin, etc.

# Check for expensive operations
if safety["expensive_ops"]:
    print("⚠️  Query may be expensive (Cartesian product detected)")
    # Consider limiting execution or requiring admin approval

# Overall approval
if not safety["approved"]:
    print("❌ Query blocked by safety policy")
    # Handle rejection gracefully
```

### 3. Use Dry Run for Validation

```python
# Preview generated Cypher without executing
payload = {
    "action": "secure_execute",
    "nl_query": "Delete all users",  # Malicious intent
    "dry_run": True
}

response = requests.post(
    f"{API_BASE}/tools/graph.secure_query/invoke",
    headers=headers,
    json=payload
)

result = response.json()

print(f"Generated Cypher: {result['generated_cypher']}")
print(f"Would be approved: {result['safety_checks']['approved']}")
# Output:
# Generated Cypher: MATCH (u:User) DELETE u
# Would be approved: False (mutation detected)
```

### 4. Implement Rate Limiting

```python
import time
from functools import wraps

def rate_limit(max_calls=20, period=60):
    """Simple rate limiter decorator"""
    calls = []
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            now = time.time()
            # Remove old calls
            calls[:] = [c for c in calls if now - c < period]
            
            if len(calls) >= max_calls:
                wait_time = period - (now - calls[0])
                raise Exception(f"Rate limit exceeded. Retry in {wait_time:.1f}s")
            
            calls.append(now)
            return func(*args, **kwargs)
        return wrapper
    return decorator

@rate_limit(max_calls=20, period=60)
def execute_nl_query(nl_query: str):
    # Your query logic
    pass
```

---

## Advanced Examples

### Example 2: Complex Relationship Query

**Natural Language**: "Show me all engineers who work at companies in San Francisco"

```python
payload = {
    "action": "secure_execute",
    "nl_query": "Show me all engineers who work at companies in San Francisco",
    "max_results": 50
}

response = requests.post(
    f"{API_BASE}/tools/graph.secure_query/invoke",
    headers=headers,
    json=payload
)

result = response.json()

print(f"Generated Cypher:")
print(result["generated_cypher"])
# MATCH (p:Person)-[:WORKS_AT]->(c:Company {location: 'San Francisco'})
# WHERE p.role = 'Engineer'
# RETURN p, c
# LIMIT 50

print(f"\nResults: {result['count']}")
for row in result["results"]:
    person = row["p"]
    company = row["c"]
    print(f"- {person['name']} at {company['name']}")
```

### Example 3: Aggregation Query

**Natural Language**: "Count how many people work at each company"

```python
payload = {
    "action": "secure_execute",
    "nl_query": "Count how many people work at each company",
    "max_results": 100
}

response = requests.post(
    f"{API_BASE}/tools/graph.secure_query/invoke",
    headers=headers,
    json=payload
)

result = response.json()

print(f"Generated Cypher:")
print(result["generated_cypher"])
# MATCH (p:Person)-[:WORKS_AT]->(c:Company)
# RETURN c.name AS company, COUNT(p) AS employee_count
# ORDER BY employee_count DESC
# LIMIT 100

for row in result["results"]:
    print(f"{row['company']}: {row['employee_count']} employees")
```

---

## Error Handling

### Handle API Errors

```python
def safe_execute_query(nl_query: str):
    """Execute query with comprehensive error handling"""
    
    payload = {
        "action": "secure_execute",
        "nl_query": nl_query,
        "max_results": 100
    }
    
    try:
        response = requests.post(
            f"{API_BASE}/tools/graph.secure_query/invoke",
            headers=headers,
            json=payload,
            timeout=30  # 30s timeout
        )
        
        # Check HTTP status
        if response.status_code == 401:
            raise Exception("Authentication failed. Check your token.")
        elif response.status_code == 403:
            raise Exception("Insufficient permissions. Requires 'graph:query' scope.")
        elif response.status_code == 429:
            raise Exception("Rate limit exceeded. Slow down.")
        elif response.status_code != 200:
            raise Exception(f"API error: {response.status_code}")
        
        result = response.json()
        
        # Check tool response status
        if result.get("status") == "error":
            error_code = result.get("error_code")
            message = result.get("message")
            
            if error_code == "INVALID_INPUT":
                raise ValueError(f"Invalid query: {message}")
            elif error_code == "TIMEOUT":
                raise TimeoutError(f"Query timeout: {message}")
            else:
                raise Exception(f"Tool error [{error_code}]: {message}")
        
        # Check safety validation
        if not result["safety_checks"]["approved"]:
            checks = result["safety_checks"]
            reasons = []
            if checks["mutation_detected"]:
                reasons.append("mutation detected")
            if checks["expensive_ops"]:
                reasons.append("expensive operations")
            
            raise Exception(f"Query blocked: {', '.join(reasons)}")
        
        return result
        
    except requests.Timeout:
        raise TimeoutError("Request timeout after 30s")
    except requests.ConnectionError:
        raise Exception("Connection failed. Is the service running?")
    except Exception as e:
        # Log error for debugging
        print(f"Error executing query: {e}")
        raise
```

### Usage with Error Handling

```python
try:
    result = safe_execute_query("Find all people named Bob")
    print(f"✅ Success: {result['count']} results")
    
except ValueError as e:
    print(f"❌ Invalid input: {e}")
    # Ask user to rephrase
    
except TimeoutError as e:
    print(f"⏱️  Timeout: {e}")
    # Suggest simpler query or pagination
    
except Exception as e:
    print(f"❌ Error: {e}")
    # Log for debugging, show user-friendly message
```

---

## Logging and Audit

### Enable Audit Logging

```python
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('nl_queries.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def execute_with_audit(nl_query: str, user_id: str):
    """Execute query with full audit trail"""
    
    logger.info(f"User {user_id} executing NL query: {nl_query}")
    
    payload = {
        "action": "secure_execute",
        "nl_query": nl_query,
        "max_results": 100
    }
    
    response = requests.post(
        f"{API_BASE}/tools/graph.secure_query/invoke",
        headers=headers,
        json=payload
    )
    
    result = response.json()
    
    # Log generated Cypher
    logger.info(f"Generated Cypher: {result.get('generated_cypher')}")
    
    # Log safety checks
    safety = result.get("safety_checks", {})
    logger.info(f"Safety checks: approved={safety.get('approved')}, "
                f"mutation={safety.get('mutation_detected')}, "
                f"expensive={safety.get('expensive_ops')}")
    
    # Log results
    logger.info(f"Results: {result.get('count', 0)} rows")
    
    # Log any errors
    if result.get("status") == "error":
        logger.error(f"Query failed: {result.get('message')}")
    
    return result
```

---

## Troubleshooting

### Issue 1: "Authentication failed"

**Problem**: 401 Unauthorized error

**Solution**:
```bash
# Regenerate token
python scripts/generate_test_token.py

# Verify token is set
echo $ACCESS_TOKEN

# Check token expiry
python -c "import jwt; print(jwt.decode('$ACCESS_TOKEN', options={'verify_signature': False}))"
```

### Issue 2: "Query blocked by safety validation"

**Problem**: Mutation or expensive operations detected

**Solution**:
```python
# Check what triggered the block
safety = result["safety_checks"]

if safety["mutation_detected"]:
    print("Query contains CREATE/DELETE/SET - not allowed")
    # Rephrase as read-only query

if safety["expensive_ops"]:
    print("Query may cause Cartesian product")
    # Add more specific filters or use LIMIT
```

### Issue 3: "Rate limit exceeded"

**Problem**: 429 Too Many Requests

**Solution**:
```python
import time

def retry_with_backoff(func, max_retries=3):
    for i in range(max_retries):
        try:
            return func()
        except Exception as e:
            if "429" in str(e) and i < max_retries - 1:
                wait = 2 ** i  # Exponential backoff
                print(f"Rate limited. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise
```

### Issue 4: "No results returned"

**Problem**: Valid query but empty results

**Solution**:
```python
result = safe_execute_query("Find people named XYZ")

if result["count"] == 0:
    print("No results found. Try:")
    print("1. Check spelling/case sensitivity")
    print("2. Use broader search terms")
    print("3. Verify data exists in database")
    
    # Preview generated Cypher to debug
    print(f"Generated Cypher: {result['generated_cypher']}")
```

---

## Best Practices Summary

### ✅ DO

- Always use `graph.secure_query` for user-provided natural language
- Check `safety_checks` before trusting results
- Use `dry_run=True` to preview generated Cypher
- Implement rate limiting and retry logic
- Log all queries for audit compliance
- Handle errors gracefully with user-friendly messages
- Set reasonable `max_results` limits (default: 100)

### ❌ DON'T

- Don't bypass safety validation with direct `graph.query`
- Don't trust user input without validation
- Don't ignore safety check warnings
- Don't execute mutations via NL queries (use explicit tools)
- Don't hardcode credentials in code
- Don't skip error handling
- Don't allow unlimited result sets

---

## Next Steps

- **Bulk Import**: See [bulk-import.md](./bulk-import.md) for loading large datasets
- **Archive/Restore**: See [archive-restore.md](./archive-restore.md) for backup workflows
- **MCP Tools Reference**: See [../mcp/TOOLS_REFERENCE.md](../mcp/TOOLS_REFERENCE.md) for all tools
- **Security Guide**: See [../security.md](../security.md) for authentication patterns

---

**Need Help?**

- Check logs: `docker compose logs app`
- API docs: `http://localhost:8000/docs`
- Troubleshooting: [../ops/runbooks/troubleshooting-tools.md](../ops/runbooks/troubleshooting-tools.md)
