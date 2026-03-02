# Cursor-Based Pagination Guide

**Version**: 1.0  
**Status**: Production  
**Last Updated**: 2025-01-15

## Overview

The Agents API uses **cursor-based pagination** for efficient, scalable list operations. Unlike offset-based pagination, cursor pagination provides:

- ✅ **Performance**: Constant-time queries regardless of page depth
- ✅ **Consistency**: Stable results during concurrent modifications
- ✅ **Scalability**: Efficient for large datasets (millions of records)
- ✅ **Simplicity**: Opaque cursors - no complex offset calculations

---

## How It Works

### Basic Flow

```
┌─────────────────────────────────────────────────────┐
│  1. Initial Request (no cursor)                     │
│     GET /agents/sessions?limit=20                   │
└─────────────────┬───────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────┐
│  2. Response with next_page_token                   │
│     {                                               │
│       "items": [...20 items...],                    │
│       "next_page_token": "eyJjcmVhdGVk..."         │
│     }                                               │
└─────────────────┬───────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────┐
│  3. Next Page Request (with cursor)                 │
│     GET /agents/sessions?limit=20&cursor=eyJjcmVh...│
└─────────────────┬───────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────┐
│  4. Response with next page                         │
│     {                                               │
│       "items": [...20 items...],                    │
│       "next_page_token": "eyJjcmVhdGVk..."  or null│
│     }                                               │
└─────────────────────────────────────────────────────┘
```

### Cursor Format

Cursors are **opaque tokens** (Base64-encoded JSON):

```json
// Decoded cursor (DO NOT rely on this format):
{
  "created_at": "2025-01-15T10:30:00.123456Z",
  "id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Important**: Always treat cursors as opaque strings. The internal format may change.

---

## Supported Endpoints

### Sessions List

**Endpoint**: `GET /v1/agents/sessions`

**Parameters**:
- `limit` (optional): Items per page (default: 20, max: 100)
- `cursor` (optional): Next page token from previous response

**Ordering**: Sessions ordered by `created_at DESC` (newest first)

**Example**:
```bash
# Page 1
curl "http://localhost:8000/v1/agents/sessions?limit=20" \
  -H "Authorization: Bearer $TOKEN"

# Page 2
curl "http://localhost:8000/v1/agents/sessions?limit=20&cursor=eyJjcmVhdGVk..." \
  -H "Authorization: Bearer $TOKEN"
```

### Steps List

**Endpoint**: `GET /v1/agents/sessions/{session_id}/steps`

**Parameters**:
- `limit` (optional): Items per page (default: 50)
- `cursor` (optional): Sequence number for next page

**Ordering**: Steps ordered by `seq ASC` (oldest first)

**Example**:
```bash
# Page 1
curl "http://localhost:8000/v1/agents/sessions/{session_id}/steps?limit=50" \
  -H "Authorization: Bearer $TOKEN"

# Page 2 (cursor is sequence number)
curl "http://localhost:8000/v1/agents/sessions/{session_id}/steps?limit=50&cursor=50" \
  -H "Authorization: Bearer $TOKEN"
```

---

## Implementation Examples

### Python

#### Basic Pagination

```python
import requests

BASE_URL = "http://localhost:8000/v1"
HEADERS = {"Authorization": f"Bearer {token}"}

def list_all_sessions():
    """Fetch all sessions using pagination."""
    all_sessions = []
    cursor = None
    
    while True:
        # Build request parameters
        params = {"limit": 50}
        if cursor:
            params["cursor"] = cursor
        
        # Make request
        response = requests.get(
            f"{BASE_URL}/agents/sessions",
            params=params,
            headers=HEADERS
        )
        response.raise_for_status()
        
        data = response.json()
        all_sessions.extend(data["items"])
        
        # Check for next page
        cursor = data.get("next_page_token")
        if not cursor:
            break  # Last page reached
    
    return all_sessions

# Usage
sessions = list_all_sessions()
print(f"Total sessions: {len(sessions)}")
```

#### Generator Pattern

```python
def paginate_sessions(limit=50):
    """Generator that yields session pages."""
    cursor = None
    
    while True:
        params = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        
        response = requests.get(
            f"{BASE_URL}/agents/sessions",
            params=params,
            headers=HEADERS
        )
        response.raise_for_status()
        
        data = response.json()
        yield data["items"]
        
        cursor = data.get("next_page_token")
        if not cursor:
            break

# Usage
for page in paginate_sessions(limit=20):
    print(f"Processing {len(page)} sessions...")
    for session in page:
        print(f"  - {session['session_id']}")
```

#### Async/Await

```python
import aiohttp

async def list_sessions_async():
    """Async pagination for high performance."""
    all_sessions = []
    cursor = None
    
    async with aiohttp.ClientSession() as session:
        while True:
            params = {"limit": 50}
            if cursor:
                params["cursor"] = cursor
            
            async with session.get(
                f"{BASE_URL}/agents/sessions",
                params=params,
                headers=HEADERS
            ) as response:
                response.raise_for_status()
                data = await response.json()
                
                all_sessions.extend(data["items"])
                
                cursor = data.get("next_page_token")
                if not cursor:
                    break
    
    return all_sessions

# Usage
import asyncio
sessions = asyncio.run(list_sessions_async())
```

---

### JavaScript/TypeScript

#### Fetch API

```typescript
interface PaginatedResponse<T> {
  items: T[];
  next_page_token?: string;
}

interface Session {
  session_id: string;
  status: string;
  created_at: string;
  // ... other fields
}

async function listAllSessions(): Promise<Session[]> {
  const allSessions: Session[] = [];
  let cursor: string | undefined;
  
  while (true) {
    const params = new URLSearchParams({ limit: "50" });
    if (cursor) {
      params.set("cursor", cursor);
    }
    
    const response = await fetch(
      `${BASE_URL}/agents/sessions?${params}`,
      {
        headers: {
          "Authorization": `Bearer ${token}`,
        },
      }
    );
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    const data: PaginatedResponse<Session> = await response.json();
    allSessions.push(...data.items);
    
    cursor = data.next_page_token;
    if (!cursor) {
      break;
    }
  }
  
  return allSessions;
}

// Usage
const sessions = await listAllSessions();
console.log(`Total sessions: ${sessions.length}`);
```

#### Async Generator

```typescript
async function* paginateSessions(
  limit: number = 50
): AsyncGenerator<Session[], void, undefined> {
  let cursor: string | undefined;
  
  while (true) {
    const params = new URLSearchParams({ limit: limit.toString() });
    if (cursor) {
      params.set("cursor", cursor);
    }
    
    const response = await fetch(
      `${BASE_URL}/agents/sessions?${params}`,
      { headers: { "Authorization": `Bearer ${token}` } }
    );
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    
    const data: PaginatedResponse<Session> = await response.json();
    yield data.items;
    
    cursor = data.next_page_token;
    if (!cursor) {
      break;
    }
  }
}

// Usage
for await (const page of paginateSessions(20)) {
  console.log(`Processing ${page.length} sessions...`);
  page.forEach(session => {
    console.log(`  - ${session.session_id}`);
  });
}
```

---

### Go

```go
package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
)

type PaginatedResponse struct {
	Items         []Session `json:"items"`
	NextPageToken *string   `json:"next_page_token,omitempty"`
}

type Session struct {
	SessionID string `json:"session_id"`
	Status    string `json:"status"`
	// ... other fields
}

func ListAllSessions(token string) ([]Session, error) {
	const baseURL = "http://localhost:8000/v1"
	var allSessions []Session
	var cursor *string

	client := &http.Client{}

	for {
		// Build URL
		u, _ := url.Parse(fmt.Sprintf("%s/agents/sessions", baseURL))
		q := u.Query()
		q.Set("limit", "50")
		if cursor != nil {
			q.Set("cursor", *cursor)
		}
		u.RawQuery = q.Encode()

		// Make request
		req, _ := http.NewRequest("GET", u.String(), nil)
		req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", token))

		resp, err := client.Do(req)
		if err != nil {
			return nil, err
		}
		defer resp.Body.Close()

		if resp.StatusCode != http.StatusOK {
			return nil, fmt.Errorf("HTTP %d", resp.StatusCode)
		}

		// Parse response
		var data PaginatedResponse
		if err := json.NewDecoder(resp.Body).Decode(&data); err != nil {
			return nil, err
		}

		allSessions = append(allSessions, data.Items...)

		// Check for next page
		if data.NextPageToken == nil {
			break
		}
		cursor = data.NextPageToken
	}

	return allSessions, nil
}

func main() {
	sessions, err := ListAllSessions(token)
	if err != nil {
		panic(err)
	}
	fmt.Printf("Total sessions: %d\n", len(sessions))
}
```

---

## Best Practices

### 1. Choose Appropriate Page Size

**Recommended**: 20-50 items per page

```python
# Good: Balanced performance
sessions = paginate(limit=50)

# Avoid: Too small (many requests)
sessions = paginate(limit=5)

# Avoid: Too large (slow responses)
sessions = paginate(limit=1000)
```

**Considerations**:
- Network latency: Larger pages reduce round trips
- Memory: Smaller pages reduce memory usage
- Timeouts: Very large pages may timeout

### 2. Handle Missing Cursors

Always check if `next_page_token` exists:

```python
data = response.json()
cursor = data.get("next_page_token")  # Returns None if missing

if cursor is None:
    print("Last page reached")
    break
```

### 3. Don't Parse Cursors

**Bad**: Relying on cursor format
```python
# DON'T DO THIS
cursor_data = json.loads(base64.b64decode(cursor))
timestamp = cursor_data["created_at"]
```

**Good**: Treat cursors as opaque
```python
# DO THIS
params = {"cursor": cursor}  # Use as-is
```

### 4. Store Cursors for Later

Cursors can be stored for resuming pagination:

```python
# Save cursor
with open("pagination_state.txt", "w") as f:
    f.write(cursor)

# Resume later
with open("pagination_state.txt", "r") as f:
    cursor = f.read().strip()

# Continue pagination
response = requests.get(url, params={"cursor": cursor})
```

### 5. Handle Errors Gracefully

```python
def safe_paginate():
    cursor = None
    retries = 0
    max_retries = 3
    
    while True:
        try:
            params = {"limit": 50}
            if cursor:
                params["cursor"] = cursor
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            yield data["items"]
            
            cursor = data.get("next_page_token")
            if not cursor:
                break
            
            retries = 0  # Reset on success
            
        except requests.Timeout:
            retries += 1
            if retries >= max_retries:
                raise
            time.sleep(2 ** retries)
        
        except requests.HTTPError as e:
            if e.response.status_code == 400:
                # Invalid cursor - restart pagination
                cursor = None
                continue
            raise
```

### 6. Combine with ETag Caching

Use ETags for efficient pagination:

```python
def paginate_with_etag():
    cursor = None
    etag = None
    
    while True:
        headers = {"Authorization": f"Bearer {token}"}
        if etag:
            headers["If-None-Match"] = etag
        
        params = {"limit": 50}
        if cursor:
            params["cursor"] = cursor
        
        response = requests.get(url, params=params, headers=headers)
        
        if response.status_code == 304:
            # Not modified - use cached data
            break
        
        etag = response.headers.get("ETag")
        data = response.json()
        
        yield data["items"]
        
        cursor = data.get("next_page_token")
        if not cursor:
            break
```

---

## Performance Considerations

### Query Efficiency

Cursor pagination uses efficient database queries:

```sql
-- Sessions (cursor = last created_at + id)
SELECT * FROM agent_sessions
WHERE (created_at, id) < (?, ?)
ORDER BY created_at DESC, id DESC
LIMIT 50;

-- Steps (cursor = last seq number)
SELECT * FROM agent_steps
WHERE session_id = ? AND seq > ?
ORDER BY seq ASC
LIMIT 50;
```

**Benefits**:
- Uses index efficiently (constant time)
- No expensive OFFSET operations
- Stable during concurrent inserts/deletes

### Memory Usage

**Server-side**: Constant memory per request (no state stored)

**Client-side**: Control memory with page size:
```python
# Low memory: Process pages as they arrive
for page in paginate_sessions(limit=20):
    process_page(page)  # Don't accumulate

# High memory: Load everything
all_sessions = []
for page in paginate_sessions():
    all_sessions.extend(page)  # Accumulate all
```

### Network Efficiency

**Multiple small requests**:
```python
# 100 requests for 1000 items (limit=10)
# Total time: 100 * 50ms = 5 seconds
```

**Fewer large requests**:
```python
# 20 requests for 1000 items (limit=50)
# Total time: 20 * 100ms = 2 seconds
```

**Recommendation**: Use `limit=50` for balanced performance

---

## Troubleshooting

### Invalid Cursor Error

**Error**:
```json
{
  "type": "https://httpstatuses.com/400",
  "title": "Invalid Cursor",
  "status": 400,
  "detail": "The provided cursor is invalid or expired.",
  "extensions": {
    "error_code": "invalid_cursor"
  }
}
```

**Causes**:
- Cursor malformed or corrupted
- Cursor from different endpoint/resource
- Very old cursor (data changed significantly)

**Solution**:
```python
try:
    response = requests.get(url, params={"cursor": cursor})
    response.raise_for_status()
except requests.HTTPError as e:
    if e.response.status_code == 400:
        # Restart pagination from beginning
        cursor = None
        response = requests.get(url, params={"limit": 50})
```

### Duplicate Items Across Pages

**Cause**: Concurrent modifications during pagination

**Mitigation**: Accept eventual consistency (rare edge case)

### Missing Items

**Cause**: Item deleted between page requests

**Mitigation**: This is expected behavior in distributed systems

---

## Comparison: Cursor vs Offset

| Feature | Cursor Pagination | Offset Pagination |
|---------|-------------------|-------------------|
| Performance | ⚡ O(1) - Constant | 🐌 O(n) - Linear |
| Scalability | ✅ Millions of records | ❌ Degrades with size |
| Consistency | ✅ Stable during changes | ❌ Can skip/duplicate |
| Simplicity | ✅ Opaque tokens | ⚠️ Manual offset math |
| Jump to page | ❌ Must traverse | ✅ Direct access |
| Sorting | ⚠️ Fixed sort order | ✅ Flexible sorting |

**Why Cursor Pagination?**

Offset pagination formula:
```sql
-- Page 1000 of results
SELECT * FROM sessions
ORDER BY created_at DESC
LIMIT 50 OFFSET 49950;  -- Database scans 50,000 rows!
```

Cursor pagination formula:
```sql
-- Any page
SELECT * FROM sessions
WHERE (created_at, id) < (?, ?)
ORDER BY created_at DESC
LIMIT 50;  -- Database uses index, scans 50 rows!
```

---

## Summary

✅ **Use cursor-based pagination** for all list endpoints  
✅ **Treat cursors as opaque** - don't parse internal format  
✅ **Choose reasonable page sizes** (20-50 items)  
✅ **Handle missing cursors** - indicates last page  
✅ **Combine with ETags** for maximum efficiency  
✅ **Implement retries** for network errors  

**Next Steps**:
- Review [Agents API Guide](./AGENTS_API_GUIDE.md)
- Review [ETag Caching Guide](./AGENTS_API_GUIDE.md#etag-caching)
- Try the [examples](#implementation-examples)
