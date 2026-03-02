# RBAC Permission Matrix

**Version**: 1.0  
**Status**: Production  
**Last Updated**: 2025-01-15

## Overview

The Agents API implements **Role-Based Access Control (RBAC)** to enforce fine-grained permissions on all operations. This document describes the permission model, roles, and access patterns.

---

## Permission Model

### Scopes

| Scope | Description | Level |
|-------|-------------|-------|
| `agents:run` | Create and manage own agent sessions | User |
| `admin:all` | Full access to all resources | Admin |

### Roles

| Role | Scopes | Access Level |
|------|--------|--------------|
| **User** | `agents:run` | Own resources only |
| **Admin** | `admin:all` | All resources (all users) |

---

## Endpoint Permissions

### Sessions

#### POST /v1/agents/sessions

**Create a new session**

| Role | Permission | Behavior |
|------|-----------|----------|
| User | ✅ Allowed | Creates session owned by user |
| Admin | ✅ Allowed | Creates session owned by admin |
| Anonymous | ❌ Denied | 401 Unauthorized |

**Required Scopes**: `agents:run` OR `admin:all`

**Example**:
```bash
# User creates their own session
curl -X POST /v1/agents/sessions \
  -H "Authorization: Bearer USER_TOKEN" \
  -d '{"manager": "auto"}'
# Result: Session with user_id=USER_ID
```

---

#### GET /v1/agents/sessions

**List sessions**

| Role | Permission | Behavior |
|------|-----------|----------|
| User | ✅ Allowed | Lists only their own sessions |
| Admin | ✅ Allowed | Lists sessions from ALL users |
| Anonymous | ❌ Denied | 401 Unauthorized |

**Required Scopes**: `agents:run` OR `admin:all`

**Filtering**:
- Users: Automatic filter `WHERE user_id = current_user_id`
- Admins: No filter (sees all sessions)

**Example**:
```bash
# User sees only their sessions
curl -X GET /v1/agents/sessions \
  -H "Authorization: Bearer USER_TOKEN"
# Result: [user's sessions only]

# Admin sees all sessions
curl -X GET /v1/agents/sessions \
  -H "Authorization: Bearer ADMIN_TOKEN"
# Result: [all users' sessions]
```

---

#### GET /v1/agents/sessions/{session_id}

**Get session by ID**

| Role | Permission | Behavior |
|------|-----------|----------|
| User (owner) | ✅ Allowed | Returns session if owned by user |
| User (non-owner) | ❌ Denied | 404 Not Found |
| Admin | ✅ Allowed | Returns any user's session |
| Anonymous | ❌ Denied | 401 Unauthorized |

**Required Scopes**: `agents:run` OR `admin:all`

**Access Control**:
```python
# Pseudocode
if not is_admin:
    if session.user_id != current_user_id:
        raise HTTPException(404, "Session not found")
```

**Example**:
```bash
# User accesses their own session
curl -X GET /v1/agents/sessions/abc123 \
  -H "Authorization: Bearer USER_TOKEN"
# Result: 200 OK (if user owns abc123)
# Result: 404 Not Found (if user doesn't own abc123)

# Admin accesses any session
curl -X GET /v1/agents/sessions/abc123 \
  -H "Authorization: Bearer ADMIN_TOKEN"
# Result: 200 OK (always, if session exists)
```

---

#### DELETE /v1/agents/sessions/{session_id}

**Cancel a session**

| Role | Permission | Behavior |
|------|-----------|----------|
| User (owner) | ✅ Allowed | Cancels session if owned by user |
| User (non-owner) | ❌ Denied | 404 Not Found |
| Admin | ✅ Allowed | Cancels any user's session |
| Anonymous | ❌ Denied | 401 Unauthorized |

**Required Scopes**: `agents:run` OR `admin:all`

**Example**:
```bash
# User cancels their own session
curl -X DELETE /v1/agents/sessions/abc123 \
  -H "Authorization: Bearer USER_TOKEN"
# Result: 204 No Content (if user owns abc123)
# Result: 404 Not Found (if user doesn't own abc123)

# Admin cancels any session
curl -X DELETE /v1/agents/sessions/xyz789 \
  -H "Authorization: Bearer ADMIN_TOKEN"
# Result: 204 No Content (always, if session exists)
```

---

### Steps

#### POST /v1/agents/sessions/{session_id}/steps

**Add step to session**

| Role | Permission | Behavior |
|------|-----------|----------|
| User (owner) | ✅ Allowed | Adds step if owns session |
| User (non-owner) | ❌ Denied | 404 Not Found |
| Admin | ✅ Allowed | Adds step to any user's session |
| Anonymous | ❌ Denied | 401 Unauthorized |

**Required Scopes**: `agents:run` OR `admin:all`

**Validation**:
1. Check session exists
2. Check user owns session (or is admin)
3. Check session is `active`

**Example**:
```bash
# User adds step to their session
curl -X POST /v1/agents/sessions/abc123/steps \
  -H "Authorization: Bearer USER_TOKEN" \
  -d '{"type": "message", "input": {}}'
# Result: 201 Created (if user owns abc123)
# Result: 404 Not Found (if user doesn't own abc123)
```

---

#### GET /v1/agents/sessions/{session_id}/steps

**List steps for session**

| Role | Permission | Behavior |
|------|-----------|----------|
| User (owner) | ✅ Allowed | Lists steps if owns session |
| User (non-owner) | ❌ Denied | 404 Not Found |
| Admin | ✅ Allowed | Lists steps for any user's session |
| Anonymous | ❌ Denied | 401 Unauthorized |

**Required Scopes**: `agents:run` OR `admin:all`

**Example**:
```bash
# User lists their session's steps
curl -X GET /v1/agents/sessions/abc123/steps \
  -H "Authorization: Bearer USER_TOKEN"
# Result: 200 OK with steps (if user owns abc123)
# Result: 404 Not Found (if user doesn't own abc123)

# Admin lists any session's steps
curl -X GET /v1/agents/sessions/xyz789/steps \
  -H "Authorization: Bearer ADMIN_TOKEN"
# Result: 200 OK with steps (always, if session exists)
```

---

### Runs

#### POST /v1/agent-runs

**Execute agent run**

| Role | Permission | Behavior |
|------|-----------|----------|
| User | ✅ Allowed | Creates run (own session or auto-creates) |
| Admin | ✅ Allowed | Creates run for any session |
| Anonymous | ❌ Denied | 401 Unauthorized |

**Required Scopes**: `agents:run` OR `admin:all`

**Session Ownership**:
- If `session_id` provided: Must own session (or be admin)
- If `session_id` omitted: Auto-creates session owned by user

**Example**:
```bash
# User creates run with their session
curl -X POST /v1/agent-runs \
  -H "Authorization: Bearer USER_TOKEN" \
  -d '{"session_id": "abc123", "prompt": "..."}'
# Result: 201 Created (if user owns abc123)
# Result: 404 Not Found (if user doesn't own abc123)

# User creates run (auto-session)
curl -X POST /v1/agent-runs \
  -H "Authorization: Bearer USER_TOKEN" \
  -d '{"prompt": "..."}'
# Result: 201 Created (creates new session owned by user)

# Admin creates run with any session
curl -X POST /v1/agent-runs \
  -H "Authorization: Bearer ADMIN_TOKEN" \
  -d '{"session_id": "xyz789", "prompt": "..."}'
# Result: 201 Created (always, if session exists)
```

---

#### GET /v1/agent-runs/{run_id}

**Get run by ID**

| Role | Permission | Behavior |
|------|-----------|----------|
| User (owner) | ✅ Allowed | Returns run if owns session |
| User (non-owner) | ❌ Denied | 404 Not Found |
| Admin | ✅ Allowed | Returns any user's run |
| Anonymous | ❌ Denied | 401 Unauthorized |

**Required Scopes**: `agents:run` OR `admin:all`

**Access Control**:
```python
# Pseudocode
if not is_admin:
    session = get_session(run.session_id)
    if session.user_id != current_user_id:
        raise HTTPException(404, "Run not found")
```

**Example**:
```bash
# User accesses their own run
curl -X GET /v1/agent-runs/run123 \
  -H "Authorization: Bearer USER_TOKEN"
# Result: 200 OK (if user owns run's session)
# Result: 404 Not Found (if user doesn't own run's session)

# Admin accesses any run
curl -X GET /v1/agent-runs/run456 \
  -H "Authorization: Bearer ADMIN_TOKEN"
# Result: 200 OK (always, if run exists)
```

---

## Access Control Matrix

### Summary Table

| Endpoint | Method | User (Owner) | User (Non-Owner) | Admin | Anonymous |
|----------|--------|--------------|------------------|-------|-----------|
| `/agents/sessions` | POST | ✅ Create own | N/A | ✅ Create own | ❌ 401 |
| `/agents/sessions` | GET | ✅ List own | N/A | ✅ List all | ❌ 401 |
| `/agents/sessions/{id}` | GET | ✅ View own | ❌ 404 | ✅ View any | ❌ 401 |
| `/agents/sessions/{id}` | DELETE | ✅ Cancel own | ❌ 404 | ✅ Cancel any | ❌ 401 |
| `/agents/sessions/{id}/steps` | POST | ✅ Add to own | ❌ 404 | ✅ Add to any | ❌ 401 |
| `/agents/sessions/{id}/steps` | GET | ✅ List own | ❌ 404 | ✅ List any | ❌ 401 |
| `/agent-runs` | POST | ✅ Create with own session | ❌ 404 | ✅ Create with any session | ❌ 401 |
| `/agent-runs/{id}` | GET | ✅ View own | ❌ 404 | ✅ View any | ❌ 401 |

---

## Implementation Details

### JWT Token Structure

```json
{
  "sub": "auth0|123456789",
  "aud": "api://cineca-agentic-platform",
  "scope": "agents:run user:me tools:invoke:basic",
  "iat": 1736687258,
  "exp": 1736773658
}
```

**Key Fields**:
- `sub`: User ID (extracted as `user_id`)
- `scope`: Space-separated scopes
- `aud`: Must match API audience

### Scope Checking

```python
# Pseudocode
def check_permission(required_scope: str, user_scopes: list[str]) -> bool:
    if "admin:all" in user_scopes:
        return True  # Admin bypass
    
    return required_scope in user_scopes

# Example
user_scopes = ["agents:run", "user:me"]
check_permission("agents:run", user_scopes)  # True
check_permission("admin:all", user_scopes)   # False
```

### User Isolation

**Database Filtering**:
```sql
-- User query (automatic filter)
SELECT * FROM agent_sessions
WHERE user_id = 'auth0|123456789'
ORDER BY created_at DESC;

-- Admin query (no filter)
SELECT * FROM agent_sessions
ORDER BY created_at DESC;
```

**Implementation**:
```python
# In repository
async def list_sessions(user_id: str, is_admin: bool, limit: int, cursor: str):
    query = select(AgentSession)
    
    # User isolation
    if not is_admin:
        query = query.where(AgentSession.user_id == user_id)
    
    query = query.order_by(AgentSession.created_at.desc())
    query = query.limit(limit)
    
    if cursor:
        query = apply_cursor(query, cursor)
    
    return await db.execute(query)
```

---

## Authentication Flow

### 1. Token Acquisition

```bash
# Get token from Auth0
curl --request POST \
  --url https://your-tenant.auth0.com/oauth/token \
  --header 'content-type: application/json' \
  --data '{
    "client_id": "YOUR_CLIENT_ID",
    "client_secret": "YOUR_CLIENT_SECRET",
    "audience": "api://cineca-agentic-platform",
    "grant_type": "client_credentials"
  }'
```

**Response**:
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "token_type": "Bearer",
  "expires_in": 86400
}
```

### 2. API Request

```bash
curl -X GET /v1/agents/sessions \
  -H "Authorization: Bearer eyJhbGciOiJSUzI1NiIs..."
```

### 3. Server Validation

```
┌──────────────────────────────────────┐
│  1. Extract Bearer token             │
└────────────┬─────────────────────────┘
             │
             ▼
┌──────────────────────────────────────┐
│  2. Verify JWT signature             │
│     - Check issuer                   │
│     - Check audience                 │
│     - Check expiration               │
└────────────┬─────────────────────────┘
             │
             ▼
┌──────────────────────────────────────┐
│  3. Extract user_id from 'sub'       │
│     e.g., "auth0|123456789"          │
└────────────┬─────────────────────────┘
             │
             ▼
┌──────────────────────────────────────┐
│  4. Extract scopes from 'scope'      │
│     e.g., "agents:run user:me"       │
└────────────┬─────────────────────────┘
             │
             ▼
┌──────────────────────────────────────┐
│  5. Check required scope             │
│     - agents:run OR admin:all        │
└────────────┬─────────────────────────┘
             │
             ▼
┌──────────────────────────────────────┐
│  6. Proceed with request             │
│     - Apply user filtering           │
│     - Or allow admin access          │
└──────────────────────────────────────┘
```

---

## Error Responses

### 401 Unauthorized

**Cause**: Missing or invalid token

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/problem+json

{
  "type": "https://httpstatuses.com/401",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Missing or invalid authentication token"
}
```

### 403 Forbidden

**Cause**: Insufficient scopes

```http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json

{
  "type": "https://httpstatuses.com/403",
  "title": "Forbidden",
  "status": 403,
  "detail": "Insufficient permissions. Required scope: agents:run",
  "extensions": {
    "required_scope": "agents:run",
    "user_scopes": ["user:me"]
  }
}
```

### 404 Not Found (Access Denied)

**Cause**: Resource exists but user doesn't have access

```http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "https://httpstatuses.com/404",
  "title": "Session Not Found",
  "status": 404,
  "detail": "Agent session 'abc123' does not exist or you don't have access to it.",
  "extensions": {
    "error_code": "session_not_found",
    "session_id": "abc123"
  }
}
```

**Note**: We return 404 instead of 403 to avoid information leakage (confirming resource existence).

---

## Best Practices

### 1. Always Use Authentication

```python
# Good: Include token
headers = {"Authorization": f"Bearer {token}"}
response = requests.get(url, headers=headers)

# Bad: Missing token
response = requests.get(url)  # 401 Unauthorized
```

### 2. Handle 404 as "Not Found or No Access"

```python
try:
    session = get_session(session_id)
except HTTPException as e:
    if e.status_code == 404:
        # Could mean:
        # 1. Session doesn't exist
        # 2. User doesn't have access
        print("Session not found or access denied")
```

### 3. Check Admin Status Before Operations

```python
def is_admin(user_scopes: list[str]) -> bool:
    return "admin:all" in user_scopes

if is_admin(scopes):
    # Can access all resources
    sessions = list_all_sessions()
else:
    # Can only access own resources
    sessions = list_my_sessions()
```

### 4. Store User Context

```python
class APIClient:
    def __init__(self, token: str):
        self.token = token
        self.user_id = self._extract_user_id(token)
        self.is_admin = self._check_admin(token)
    
    def _extract_user_id(self, token: str) -> str:
        import jwt
        decoded = jwt.decode(token, options={"verify_signature": False})
        return decoded["sub"]
    
    def _check_admin(self, token: str) -> bool:
        import jwt
        decoded = jwt.decode(token, options={"verify_signature": False})
        scopes = decoded.get("scope", "").split()
        return "admin:all" in scopes
```

---

## Testing RBAC

### Test User Access

```python
import pytest

def test_user_can_access_own_session(user_token, session_id):
    """User can access their own session."""
    response = requests.get(
        f"/v1/agents/sessions/{session_id}",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert response.status_code == 200

def test_user_cannot_access_other_session(user_token, other_session_id):
    """User cannot access another user's session."""
    response = requests.get(
        f"/v1/agents/sessions/{other_session_id}",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert response.status_code == 404
```

### Test Admin Access

```python
def test_admin_can_access_any_session(admin_token, any_session_id):
    """Admin can access any user's session."""
    response = requests.get(
        f"/v1/agents/sessions/{any_session_id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200

def test_admin_can_list_all_sessions(admin_token):
    """Admin sees sessions from all users."""
    response = requests.get(
        "/v1/agents/sessions",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    
    sessions = response.json()["items"]
    user_ids = {s["user_id"] for s in sessions}
    
    # Should have sessions from multiple users
    assert len(user_ids) > 1
```

### Test User Isolation

```python
def test_users_cannot_see_each_other(user1_token, user2_token):
    """Users see only their own sessions."""
    # User 1 creates session
    resp1 = requests.post(
        "/v1/agents/sessions",
        json={"manager": "auto"},
        headers={"Authorization": f"Bearer {user1_token}"}
    )
    session1_id = resp1.json()["session_id"]
    
    # User 2 cannot access User 1's session
    resp2 = requests.get(
        f"/v1/agents/sessions/{session1_id}",
        headers={"Authorization": f"Bearer {user2_token}"}
    )
    assert resp2.status_code == 404
```

---

## Security Considerations

### 1. Information Leakage

**Problem**: Returning 403 confirms resource exists

```python
# Bad: Leaks information
if not user_owns_session(session_id, user_id):
    raise HTTPException(403, "Forbidden")  # Confirms session exists!

# Good: Return 404 for both cases
if not session_exists(session_id):
    raise HTTPException(404, "Session not found")

if not user_owns_session(session_id, user_id):
    raise HTTPException(404, "Session not found")  # Same error!
```

### 2. Token Storage

**Never**:
- ❌ Store tokens in localStorage (XSS vulnerable)
- ❌ Log tokens in plaintext
- ❌ Commit tokens to version control

**Do**:
- ✅ Store in httpOnly cookies (for web apps)
- ✅ Store in secure keychain (for mobile/desktop)
- ✅ Use environment variables (for server-side)

### 3. Token Expiration

**Handle expired tokens**:
```python
def api_request_with_refresh(url, token_manager):
    try:
        response = requests.get(url, headers={"Authorization": f"Bearer {token_manager.token}"})
        response.raise_for_status()
        return response.json()
    except HTTPException as e:
        if e.status_code == 401:
            # Token expired - refresh
            token_manager.refresh()
            response = requests.get(url, headers={"Authorization": f"Bearer {token_manager.token}"})
            return response.json()
        raise
```

### 4. Scope Minimization

**Principle**: Request minimum required scopes

```bash
# Good: Request only what you need
scope="agents:run user:me"

# Bad: Request everything
scope="agents:run admin:all user:me tools:invoke:*"
```

---

## Summary

✅ **Two-tier access model**: Users (own resources) + Admins (all resources)  
✅ **Scope-based authorization**: `agents:run` for users, `admin:all` for admins  
✅ **User isolation**: Automatic filtering by `user_id`  
✅ **404 for access denial**: Prevents information leakage  
✅ **JWT-based authentication**: Stateless token validation  
✅ **Secure by default**: All endpoints require authentication  

**Next Steps**:
- Review [Agents API Guide](./AGENTS_API_GUIDE.md)
- Review [Authentication Documentation](./AUTHENTICATION_FIX_COMPLETE.md)
- Try [RBAC tests](#testing-rbac)
