# Idempotency Guide

**Version**: 1.0  
**Status**: Production  
**Last Updated**: 2025-01-15

## Overview

**Idempotency** ensures that multiple identical requests have the same effect as a single request. This is critical for:

- ✅ **Safe Retries**: Network failures, timeouts
- ✅ **Duplicate Prevention**: Accidental double-clicks, race conditions
- ✅ **Distributed Systems**: Message queue processing, webhooks
- ✅ **Client Resilience**: Automatic retry logic without side effects

---

## How It Works

### The Idempotency-Key Header

Clients send a unique key with each request:

```http
POST /v1/agents/sessions
Authorization: Bearer <token>
Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000
Content-Type: application/json

{
  "manager": "auto",
  "tools": ["calculator"]
}
```

### First Request

Server processes request normally:

```http
HTTP/1.1 201 Created
Location: /v1/agents/sessions/abc123
Content-Type: application/json

{
  "session_id": "abc123",
  "manager": "auto",
  "tools": ["calculator"],
  ...
}
```

**No** `Idempotency-Replayed` header = fresh request

### Subsequent Requests (Same Key)

Server returns **cached response**:

```http
HTTP/1.1 201 Created
Idempotency-Replayed: true
Location: /v1/agents/sessions/abc123
Content-Type: application/json

{
  "session_id": "abc123",
  "manager": "auto",
  "tools": ["calculator"],
  ...
}
```

**With** `Idempotency-Replayed: true` = replayed response

**Key Points**:
- Same HTTP status code (201)
- Same response body
- Same resource ID (`abc123`)
- Added `Idempotency-Replayed: true` header
- **No new resource created**

---

## Supported Endpoints

### ✅ POST /v1/agents/sessions

Create agent session with idempotency.

**Example**:
```bash
curl -X POST http://localhost:8000/v1/agents/sessions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Idempotency-Key: $(uuidgen)" \
  -H "Content-Type: application/json" \
  -d '{
    "manager": "auto",
    "tools": ["calculator"]
  }'
```

### ✅ POST /v1/agents/sessions/{session_id}/steps

Add step to session with idempotency.

**Example**:
```bash
curl -X POST http://localhost:8000/v1/agents/sessions/{id}/steps \
  -H "Authorization: Bearer $TOKEN" \
  -H "Idempotency-Key: $(uuidgen)" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "message",
    "input": {"text": "Hello"},
    "output": {"response": "Hi"}
  }'
```

### ✅ POST /v1/agent-runs

Execute agent run with idempotency.

**Example**:
```bash
curl -X POST http://localhost:8000/v1/agent-runs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Idempotency-Key: $(uuidgen)" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "abc123",
    "prompt": "Calculate 2+2",
    "manager": "auto"
  }'
```

---

## Key Format Requirements

### Recommended: UUID v4

```python
import uuid

idempotency_key = str(uuid.uuid4())
# Example: "550e8400-e29b-41d4-a716-446655440000"
```

### Requirements

- **Max Length**: 255 characters
- **Uniqueness**: Must be unique per logical operation
- **Case-Sensitive**: `abc` ≠ `ABC`
- **No Special Meaning**: Server doesn't interpret key content

### Valid Formats

```bash
# UUID v4 (recommended)
550e8400-e29b-41d4-a716-446655440000

# Timestamp + random
20250115T103000Z-abc123def456

# Custom format
user123-request456-retry789
```

### Invalid Keys

```bash
# Too short (not unique enough)
123

# Contains spaces (avoid)
"my key 123"

# Too long (>255 chars)
aaa...aaa (300 characters)
```

---

## Implementation Examples

### Python

#### Basic Usage

```python
import requests
import uuid

BASE_URL = "http://localhost:8000/v1"
TOKEN = "your_token_here"

def create_session_idempotent(data):
    """Create session with idempotency."""
    idempotency_key = str(uuid.uuid4())
    
    response = requests.post(
        f"{BASE_URL}/agents/sessions",
        json=data,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Idempotency-Key": idempotency_key,
            "Content-Type": "application/json",
        },
    )
    
    response.raise_for_status()
    
    # Check if replayed
    is_replayed = response.headers.get("Idempotency-Replayed") == "true"
    if is_replayed:
        print("Response was replayed from cache")
    else:
        print("Fresh request - resource created")
    
    return response.json()

# Usage
session = create_session_idempotent({
    "manager": "auto",
    "tools": ["calculator"],
})
print(f"Session ID: {session['session_id']}")
```

#### Automatic Retry with Same Key

```python
import time

def create_session_with_retry(data, max_retries=3):
    """Retry on failure using same idempotency key."""
    idempotency_key = str(uuid.uuid4())
    
    for attempt in range(max_retries):
        try:
            response = requests.post(
                f"{BASE_URL}/agents/sessions",
                json=data,
                headers={
                    "Authorization": f"Bearer {TOKEN}",
                    "Idempotency-Key": idempotency_key,  # Same key!
                },
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
            
        except requests.Timeout:
            print(f"Timeout on attempt {attempt + 1}, retrying...")
            time.sleep(2 ** attempt)  # Exponential backoff
            
        except requests.RequestException as e:
            if attempt == max_retries - 1:
                raise
            print(f"Error on attempt {attempt + 1}: {e}")
            time.sleep(2 ** attempt)
    
    raise Exception("Max retries exceeded")

# Usage
session = create_session_with_retry({
    "manager": "auto",
    "tools": ["calculator"],
})
```

#### Context Manager for Idempotency

```python
from contextlib import contextmanager

@contextmanager
def idempotent_request():
    """Context manager that generates and tracks idempotency key."""
    key = str(uuid.uuid4())
    print(f"Using idempotency key: {key}")
    
    try:
        yield key
    finally:
        print(f"Request completed with key: {key}")

# Usage
with idempotent_request() as key:
    response = requests.post(
        f"{BASE_URL}/agents/sessions",
        json={"manager": "auto", "tools": []},
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Idempotency-Key": key,
        },
    )
```

---

### JavaScript/TypeScript

#### Fetch API

```typescript
interface IdempotentRequestOptions {
  method: string;
  body?: any;
  idempotencyKey?: string;
}

async function idempotentRequest<T>(
  url: string,
  options: IdempotentRequestOptions
): Promise<T> {
  const idempotencyKey = options.idempotencyKey || crypto.randomUUID();
  
  const response = await fetch(url, {
    method: options.method,
    headers: {
      "Authorization": `Bearer ${token}`,
      "Idempotency-Key": idempotencyKey,
      "Content-Type": "application/json",
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
  }
  
  const isReplayed = response.headers.get("Idempotency-Replayed") === "true";
  console.log(isReplayed ? "Response replayed" : "Fresh request");
  
  return await response.json();
}

// Usage
const session = await idempotentRequest("/v1/agents/sessions", {
  method: "POST",
  body: {
    manager: "auto",
    tools: ["calculator"],
  },
});
```

#### Retry with Same Key

```typescript
async function createSessionWithRetry(
  data: any,
  maxRetries: number = 3
): Promise<any> {
  const idempotencyKey = crypto.randomUUID();
  
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      const response = await fetch(`${BASE_URL}/agents/sessions`, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${token}`,
          "Idempotency-Key": idempotencyKey,  // Same key across retries
          "Content-Type": "application/json",
        },
        body: JSON.stringify(data),
      });
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      
      return await response.json();
      
    } catch (error) {
      console.log(`Attempt ${attempt + 1} failed: ${error}`);
      
      if (attempt < maxRetries - 1) {
        const delay = Math.pow(2, attempt) * 1000;  // Exponential backoff
        await new Promise(resolve => setTimeout(resolve, delay));
      } else {
        throw error;
      }
    }
  }
}
```

---

### Go

```go
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	"github.com/google/uuid"
)

type SessionRequest struct {
	Manager     string   `json:"manager"`
	Tools       []string `json:"tools"`
	Temperature float64  `json:"temperature,omitempty"`
}

type SessionResponse struct {
	SessionID string   `json:"session_id"`
	Manager   string   `json:"manager"`
	Tools     []string `json:"tools"`
	Status    string   `json:"status"`
}

func createSessionWithRetry(
	baseURL, token string,
	data SessionRequest,
	maxRetries int,
) (*SessionResponse, error) {
	idempotencyKey := uuid.New().String()
	
	for attempt := 0; attempt < maxRetries; attempt++ {
		// Marshal request body
		body, err := json.Marshal(data)
		if err != nil {
			return nil, err
		}
		
		// Create request
		req, err := http.NewRequest(
			"POST",
			fmt.Sprintf("%s/agents/sessions", baseURL),
			bytes.NewBuffer(body),
		)
		if err != nil {
			return nil, err
		}
		
		// Set headers (same idempotency key for all retries)
		req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", token))
		req.Header.Set("Idempotency-Key", idempotencyKey)
		req.Header.Set("Content-Type", "application/json")
		
		// Make request
		client := &http.Client{Timeout: 10 * time.Second}
		resp, err := client.Do(req)
		if err != nil {
			fmt.Printf("Attempt %d failed: %v\n", attempt+1, err)
			if attempt < maxRetries-1 {
				time.Sleep(time.Duration(1<<attempt) * time.Second)
				continue
			}
			return nil, err
		}
		defer resp.Body.Close()
		
		// Check status
		if resp.StatusCode != http.StatusCreated {
			return nil, fmt.Errorf("HTTP %d", resp.StatusCode)
		}
		
		// Check if replayed
		isReplayed := resp.Header.Get("Idempotency-Replayed") == "true"
		if isReplayed {
			fmt.Println("Response replayed from cache")
		} else {
			fmt.Println("Fresh request - resource created")
		}
		
		// Parse response
		var session SessionResponse
		if err := json.NewDecoder(resp.Body).Decode(&session); err != nil {
			return nil, err
		}
		
		return &session, nil
	}
	
	return nil, fmt.Errorf("max retries exceeded")
}

func main() {
	session, err := createSessionWithRetry(
		"http://localhost:8000/v1",
		token,
		SessionRequest{
			Manager: "auto",
			Tools:   []string{"calculator"},
		},
		3,
	)
	if err != nil {
		panic(err)
	}
	fmt.Printf("Session ID: %s\n", session.SessionID)
}
```

---

## Best Practices

### 1. Generate Fresh Keys per Logical Operation

**Good**: New key per operation
```python
# First session
session1 = create_session(key=uuid.uuid4())

# Second session (different operation)
session2 = create_session(key=uuid.uuid4())  # New key!
```

**Bad**: Reusing keys across operations
```python
key = uuid.uuid4()
session1 = create_session(key=key)
session2 = create_session(key=key)  # Same key - returns session1!
```

### 2. Reuse Key Only for Retries

**Good**: Same key for retry
```python
key = uuid.uuid4()
try:
    response = create_session(key=key)
except Timeout:
    # Retry with same key
    response = create_session(key=key)  # Safe!
```

### 3. Store Keys for Debugging

```python
import logging

def create_session_with_logging(data):
    key = str(uuid.uuid4())
    
    # Log key for debugging
    logging.info(f"Creating session with idempotency key: {key}")
    
    try:
        response = requests.post(url, json=data, headers={"Idempotency-Key": key})
        logging.info(f"Session created: {response.json()['session_id']}")
        return response.json()
    except Exception as e:
        logging.error(f"Failed to create session (key: {key}): {e}")
        raise
```

### 4. Handle Replayed Responses

```python
response = requests.post(url, json=data, headers={"Idempotency-Key": key})

is_replayed = response.headers.get("Idempotency-Replayed") == "true"

if is_replayed:
    # Resource already exists - safe to continue
    print("Operation already completed (idempotent retry)")
else:
    # Fresh request - new resource created
    print("New resource created")

# Both cases: use response data
session_id = response.json()["session_id"]
```

### 5. Don't Use Idempotency for GET/DELETE

**Not Needed**:
- GET requests are naturally idempotent
- DELETE requests are already idempotent by design

**Only Use For**:
- ✅ POST requests (create operations)
- ❌ GET requests (no side effects)
- ❌ DELETE requests (already idempotent)
- ❌ PATCH/PUT requests (not implemented yet)

### 6. Key Expiration Awareness

Idempotency keys expire after **24 hours**.

```python
# Day 1
key = str(uuid.uuid4())
session1 = create_session(key=key)  # Fresh

# Day 2 (after 24 hours)
session2 = create_session(key=key)  # Fresh again (key expired)
```

**Impact**:
- Keys cached for 24 hours in Redis
- After expiration: same key treated as fresh
- **Best Practice**: Always generate new keys

---

## Error Scenarios

### Missing Idempotency-Key

**Behavior**: Request processed normally (no idempotency protection)

```bash
curl -X POST /v1/agents/sessions \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"manager": "auto"}'
# No Idempotency-Key header

# Every request creates new session
```

**Recommendation**: Always include `Idempotency-Key` for create operations

### Invalid Key Format

**Error**: None - any string accepted (max 255 chars)

```python
# Valid (but not recommended)
headers = {"Idempotency-Key": "my-custom-key-123"}

# Invalid (too long)
headers = {"Idempotency-Key": "a" * 300}  # Error: Key too long
```

### Concurrent Requests (Same Key)

**Scenario**: Two requests arrive simultaneously with same key

**Behavior**:
1. First request: Processes normally
2. Second request: Waits for first to complete (lock)
3. Second request: Returns cached response

**Implementation**: Redis locks prevent race conditions

```python
# Thread 1 and Thread 2 both call with same key
key = "abc123"

# Thread 1: Acquires lock, processes request
# Thread 2: Waits for lock, then returns cached response
```

---

## Implementation Details

### Server-Side Flow

```
┌─────────────────────────────────────────────────┐
│  1. Receive Request with Idempotency-Key        │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│  2. Check Redis Cache for Key                   │
│     - Cache Hit: Return cached response          │
│     - Cache Miss: Continue to step 3             │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│  3. Acquire Lock on Key (prevent races)         │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│  4. Double-Check Cache (another request may     │
│     have completed while waiting for lock)      │
│     - Cache Hit: Return cached response          │
│     - Cache Miss: Continue to step 5             │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│  5. Process Request (create resource)           │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│  6. Cache Response in Redis                     │
│     - TTL: 24 hours                              │
│     - Key: idempotency:{key}                     │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│  7. Release Lock                                 │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│  8. Return Response to Client                   │
└─────────────────────────────────────────────────┘
```

### Storage

**PostgreSQL Table**: `idempotency_keys`
```sql
CREATE TABLE idempotency_keys (
    id UUID PRIMARY KEY,
    key VARCHAR(255) NOT NULL UNIQUE,
    user_id VARCHAR(255) NOT NULL,
    endpoint VARCHAR(255) NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    response_status INT NOT NULL,
    response_body JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE INDEX idx_idempotency_keys_key ON idempotency_keys(key);
CREATE INDEX idx_idempotency_keys_created_at ON idempotency_keys(created_at);
```

**Redis Cache**:
```
Key:   idempotency:{idempotency_key}
Value: {status: 201, body: {...}, headers: {...}}
TTL:   86400 seconds (24 hours)
```

### Security

**User Isolation**: Idempotency keys scoped per user

```python
# User A creates session with key "abc123"
user_a_session = create_session(key="abc123")  # Creates new

# User B creates session with same key "abc123"
user_b_session = create_session(key="abc123")  # Also creates new!
```

**Prevents**:
- Cross-user key collisions
- Information leakage between users

---

## Monitoring and Debugging

### Check if Response Was Replayed

```python
response = requests.post(url, json=data, headers={"Idempotency-Key": key})

if response.headers.get("Idempotency-Replayed") == "true":
    print(f"⚠️  Replayed response for key: {key}")
    print(f"   Resource ID: {response.json()['session_id']}")
else:
    print(f"✅ Fresh request for key: {key}")
```

### Metrics to Track

```python
# Client-side metrics
total_requests = 0
replayed_requests = 0

def track_idempotency(response):
    global total_requests, replayed_requests
    total_requests += 1
    
    if response.headers.get("Idempotency-Replayed") == "true":
        replayed_requests += 1
    
    replay_rate = (replayed_requests / total_requests) * 100
    print(f"Replay rate: {replay_rate:.1f}%")
```

**Expected Replay Rates**:
- Normal operation: 0-5% (retries only)
- High network instability: 10-20%
- Duplicate clicks: 20-50%

### Debug Logging

```python
import logging

logging.basicConfig(level=logging.DEBUG)

key = str(uuid.uuid4())
logging.debug(f"Generated idempotency key: {key}")

response = requests.post(url, json=data, headers={"Idempotency-Key": key})

logging.debug(f"Response status: {response.status_code}")
logging.debug(f"Idempotency-Replayed: {response.headers.get('Idempotency-Replayed')}")
logging.debug(f"Resource ID: {response.json()['session_id']}")
```

---

## Summary

✅ **Use Idempotency-Key header** for all POST operations  
✅ **Generate UUID v4 keys** for uniqueness  
✅ **Reuse keys only for retries** of same operation  
✅ **Check Idempotency-Replayed header** to detect replays  
✅ **Keys expire after 24 hours** - generate fresh keys  
✅ **User-scoped isolation** prevents cross-user collisions  

**Next Steps**:
- Review [Agents API Guide](./AGENTS_API_GUIDE.md)
- Review [Error Handling Guide](./ERROR_HANDLING_STANDARDIZATION.md)
- Try the [implementation examples](#implementation-examples)
