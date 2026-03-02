# Agent API Endpoints - Quick Reference Card

> **Last Updated:** October 20, 2025  
> **All descriptions have been rewritten in simple, human-friendly language**

---

## Session Management Endpoints

### 1️⃣ POST /v1/agents/sessions
**Create a new agent session**

```
Purpose: Start a long-running conversation with context persistence
Returns: 201 Created (includes session_id and full session details)
Returns: 400 Bad Request (invalid parameters)
Returns: 409 Conflict (session_id already exists)
```

**Why:** Setup LLM configuration, track related tasks, enable pausing/continuing work  
**How:** Create session with optional ID (idempotent), get back session details  
**Access:** Users create their own; admins can create for others  
**Special:** Supports Idempotency-Key header for safe retries

---

### 2️⃣ GET /v1/agents/sessions
**List agent sessions**

```
Purpose: Find and monitor all your sessions
Returns: 200 OK (paginated list with next_cursor)
Returns: 304 Not Modified (if ETag matches)
```

**Why:** Discover existing sessions, track work status, review history  
**How:** Paginated results (cursor-based, limit=20 default), ordered by most recent  
**Access:** Users see only theirs; admins see all  
**Special:** ETag caching, rate limited, includes status/dates

---

### 3️⃣ GET /v1/agents/sessions/{session_id}
**Get session details**

```
Purpose: Check status and view configuration of a specific session
Returns: 200 OK (full session details)
Returns: 304 Not Modified (if ETag matches)
Returns: 404 Not Found (session doesn't exist or no permission)
```

**Why:** Check if session is active, view settings, track progress via last step ID  
**How:** Fetch session by ID with ownership validation  
**Access:** Users see only their own; admins can see any  
**Special:** Includes ETag for caching

---

### 4️⃣ DELETE /v1/agents/sessions/{session_id}
**Cancel agent session**

```
Purpose: Stop a session and halt ongoing work
Returns: 204 No Content (success - no response body)
Returns: 404 Not Found (session doesn't exist or no permission)
```

**Why:** Stop runaway sessions, clean up resources, gracefully exit  
**How:** Send DELETE request (idempotent - safe to call multiple times)  
**Access:** Users cancel their own; admins can cancel any  
**Special:** Best-effort (no guarantee of immediate stop), idempotent

---

## Session Steps Endpoints

### 5️⃣ GET /v1/agents/sessions/{session_id}/steps
**List session steps**

```
Purpose: View all steps in a session's history
Returns: 200 OK (paginated list of steps with next_cursor)
Returns: 304 Not Modified (if ETag matches)
Returns: 404 Not Found (session doesn't exist or no permission)
```

**Why:** Track what agent did, debug by examining steps, review progression  
**How:** Paginated results (cursor-based, limit=50 default), ordered oldest-to-newest  
**Access:** Users see steps from their own sessions; admins see any  
**Special:** Each step shows type, message, tool, input/output, status, timestamps

---

### 6️⃣ POST /v1/agents/sessions/{session_id}/steps
**Add step to session**

```
Purpose: Submit a new step (message, tool input, etc.) to a session
Returns: 201 Created (step created with assigned ID and sequence)
Returns: 400 Bad Request (invalid step type, session not active, etc.)
Returns: 404 Not Found (session doesn't exist or no permission)
```

**Why:** Add user messages, submit tool inputs, feed results back to agent  
**How:** POST with step type, message/tool/input/output as needed  
**Access:** Users add to their own sessions; admins to any  
**Special:** Auto-sequencing, type validation, idempotency support, session must be active

**Allowed Step Types:** `message`, `user`, `assistant`, `tool`, `system`, `error`

---

## Agent Runs Endpoints

### 7️⃣ POST /v1/agent-runs
**Create an agent run**

```
Purpose: Execute a one-off agent task (optional: linked to session)
Returns: 201 Created (run completed with output, metrics, trace info)
Returns: 400 Bad Request (invalid parameters)
Returns: 404 Not Found (if session_id provided but doesn't exist)
```

**Why:** Solve simple tasks without session overhead, get quick results  
**How:** POST with prompt; auto-creates session if session_id not provided  
**Access:** Users create runs; admins can create on behalf of others  
**Special:** Idempotency support, latency tracking, audit logging, auto-session creation

---

### 8️⃣ GET /v1/agent-runs/{run_id}
**Get agent run by ID**

```
Purpose: Retrieve results of a previously-created agent run
Returns: 200 OK (run details with output, metrics, trace info)
Returns: 304 Not Modified (if ETag matches)
Returns: 404 Not Found (run doesn't exist or no permission)
```

**Why:** Check results from earlier runs, access output, debug via trace IDs  
**How:** Fetch run by ID with ownership validation  
**Access:** Users see their own runs; admins see any  
**Special:** Includes latency, model used, trace_id, event_id, session_id if linked

---

## Common Features Across All Endpoints

### 🔐 Authentication & Authorization
- **All endpoints** require Bearer token (HTTP Bearer authentication)
- **Users** see only their own resources
- **Admins** (with `admin:all` scope) see all resources

### 💾 Caching & Performance
- **GET endpoints** support ETag-based caching
- Include `If-None-Match: {etag}` header to get 304 Not Modified if unchanged
- Saves bandwidth by avoiding redundant data transfers

### 🔄 Idempotency
- **POST endpoints** support `Idempotency-Key` header
- Send same key twice → get same response without side effects
- Safe for unreliable networks

### 📊 Pagination
- **List endpoints** use cursor-based pagination
- `limit` parameter (default varies by endpoint)
- `cursor` parameter for next page (from `next_cursor` in response)

### ⏱️ Rate Limiting
- **All endpoints** subject to per-user rate limiting
- Response headers include: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`

### 🔍 Error Handling
- **All errors** return RFC 7807 Problem Detail format
- Status codes: 400 (bad request), 404 (not found), 401 (unauthorized), 403 (forbidden), 500 (server error)

### 📝 Response Headers
- `X-Request-Id` – Request tracking ID
- `X-Correlation-Id` – Correlation ID for debugging
- `Location` – URL of created resource (for 201 responses)
- `ETag` – Entity tag for cache validation
- `Idempotency-Replayed` – Present if request replayed from cache

---

## Usage Examples

### Create a Session and Add Steps

```bash
# 1. Create session
SESSION_ID=$(curl -s -X POST http://localhost:8000/v1/agents/sessions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "temperature": 0.2,
    "max_steps": 10,
    "tools": ["web_search"]
  }' | jq -r '.session_id')

# 2. Add a user message step
curl -X POST http://localhost:8000/v1/agents/sessions/$SESSION_ID/steps \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "message",
    "message": "Search for latest AI trends"
  }'

# 3. List steps
curl -X GET http://localhost:8000/v1/agents/sessions/$SESSION_ID/steps \
  -H "Authorization: Bearer $TOKEN"

# 4. Cancel session
curl -X DELETE http://localhost:8000/v1/agents/sessions/$SESSION_ID \
  -H "Authorization: Bearer $TOKEN"
```

### One-Off Run vs Session-Based

```bash
# One-off: No session management
curl -X POST http://localhost:8000/v1/agent-runs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is AI?"}'

# Session-based: Manage conversation
# ... create session, add steps, check status, cancel, etc.
```

---

## Key Differences: Runs vs Sessions

| Aspect | Agent Runs | Sessions |
|--------|-----------|----------|
| **Use Case** | One-off tasks | Long-running conversations |
| **Session Required** | Optional (auto-creates) | Required (you create it) |
| **Lifespan** | Single execution | Multiple steps over time |
| **Steps** | Included in response | Managed separately |
| **Context Persistence** | Limited | Full context across steps |
| **Cancellation** | N/A (completes immediately) | Can be cancelled mid-execution |

---

## Status Codes Reference

| Code | Meaning | Common Reasons |
|------|---------|-----------------|
| 200 | OK | GET succeeded, resource found |
| 201 | Created | POST succeeded, resource created |
| 204 | No Content | DELETE succeeded, no body returned |
| 304 | Not Modified | ETag matched, use cached version |
| 400 | Bad Request | Invalid parameters, type validation failed |
| 401 | Unauthorized | Missing or invalid token |
| 403 | Forbidden | Insufficient permissions |
| 404 | Not Found | Resource doesn't exist or inaccessible |
| 409 | Conflict | Resource already exists (session_id collision) |
| 422 | Validation Error | Request body validation failed |
| 500 | Server Error | Internal server error |

---

## Documentation Access

- **Swagger UI** (interactive): http://localhost:8000/docs
- **ReDoc** (read-only): http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

---

**All descriptions written in simple, straightforward, human-friendly language.**  
**Last verified:** October 20, 2025
