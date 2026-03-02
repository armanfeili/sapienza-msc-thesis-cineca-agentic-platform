# User Token Scope Issue - RESOLUTION GUIDE

**Date**: January 17, 2025  
**Issue**: USER_TOKEN getting 403 Forbidden on model instance endpoints  
**Status**: ⚠️ **TOKEN NEEDS TO BE REGENERATED WITH CORRECT SCOPES**

---

## 🔍 Problem Analysis

The current USER_TOKEN from Auth0 is **missing required scopes** for model instance endpoints.

### Current Token Scopes ❌
```json
{
  "scope": "user:me tools:invoke:basic"
}
```

### Required Scopes for Model Endpoints ✅
```json
{
  "scope": "user:me tools:invoke:basic models:read models:test models:defaults:read models:defaults:write:self"
}
```

---

## 📋 Endpoint Permission Requirements

| Endpoint | Method | Required Scope | Current Token Has? |
|----------|--------|---------------|-------------------|
| `/v1/models/instances` | GET | `models:read` or `admin:all` | ❌ NO |
| `/v1/models/instances/{id}` | GET | `models:read` or `admin:all` | ❌ NO |
| `/v1/models/instances/{id}/tests` | POST | `models:test` or `admin:all` | ❌ NO |
| `/v1/models/defaults` | GET | `models:defaults:read` or `admin:all` | ❌ NO |
| `/v1/models/defaults` | PATCH | `models:defaults:write:self` or `admin:all` | ❌ NO |

**Result**: All model endpoints return **403 Forbidden** because the token lacks required scopes.

---

## 🔧 Solution Options

### Option 1: Get New Token from Auth0 (RECOMMENDED)

**Use the provided script** to request a new token with correct scopes:

```bash
./get_auth0_tokens_with_model_scopes.sh
```

This script will:
1. Prompt for admin credentials
2. Request admin token with `user:me tools:invoke:all admin:all`
3. Prompt for user credentials  
4. Request user token with `user:me tools:invoke:basic models:read models:test models:defaults:read models:defaults:write:self`
5. Display export commands

**Then copy the export commands** and use the new tokens.

### Option 2: Manual Auth0 Token Request

If you prefer to request manually:

```bash
curl --request POST \
  --url 'https://cineca.eu.auth0.com/oauth/token' \
  --header 'content-type: application/json' \
  --data '{
    "grant_type": "password",
    "username": "user@cineca.local",
    "password": "YOUR_PASSWORD",
    "audience": "api://cineca-agentic-platform",
    "client_id": "kwkf1bGn2NmdKWzioZYkvtYM022dzb5C",
    "scope": "user:me tools:invoke:basic models:read models:test models:defaults:read models:defaults:write:self"
  }'
```

### Option 3: Update Auth0 API Settings

If Auth0 rejects the model scopes, you need to:

1. **Go to Auth0 Dashboard** → APIs → `cineca-agentic-platform`
2. **Add permissions/scopes**:
   - `models:read` - Read model instances
   - `models:test` - Test model instances
   - `models:defaults:read` - Read default models
   - `models:defaults:write:self` - Write own default models
3. **Assign scopes to users** (or make them default for all users)
4. **Request new token** with the added scopes

---

## ✅ Verification

After getting the new token, verify it works:

```bash
# Set the new token
export USER_TOKEN="<your-new-token>"

# Test GET /v1/models/instances
curl -X GET "http://localhost:8000/v1/models/instances" \
  -H "Authorization: Bearer $USER_TOKEN" | jq

# Should return 200 OK with list of instances (or empty array)
```

### Expected Results ✅

| Endpoint | Expected Status | Expected Response |
|----------|----------------|-------------------|
| `GET /v1/models/instances` | 200 OK | `{"instances": [...], "total": N, "page_size": 100}` |
| `GET /v1/models/defaults` | 200 OK or 404 | Default model or "No default configured" |
| `POST /v1/models/instances/{id}/tests` | 200 OK or 404 | Test result or "Instance not found" |

---

## 🔍 Token Inspection

To check what scopes a token has:

```bash
# Decode token (without verification)
python3 -c "
import jwt
token = '$USER_TOKEN'
payload = jwt.decode(token, options={'verify_signature': False})
print('Scopes:', payload.get('scope', 'NONE'))
"
```

**Current USER_TOKEN scopes:**
```
user:me tools:invoke:basic
```

**Required scopes:**
```
user:me tools:invoke:basic models:read models:test models:defaults:read models:defaults:write:self
```

---

## 📝 Scope Definitions

| Scope | Description | Allows |
|-------|-------------|--------|
| `user:me` | User identity | Access own profile info |
| `tools:invoke:basic` | Basic tool usage | Invoke basic tools |
| `models:read` | Read model instances | List and get model instances (enabled only for users) |
| `models:test` | Test model instances | Send test prompts to instances |
| `models:defaults:read` | Read defaults | Get default model (user → tenant → global precedence) |
| `models:defaults:write:self` | Write own defaults | Set personal default model |
| **Admin Scopes** | | |
| `admin:all` | Full admin access | All permissions (wildcard, bypasses all checks) |
| `models:write` | Create instances | Create new model instances (admin only) |
| `models:delete` | Delete instances | Delete model instances (admin only) |
| `models:defaults:write:tenant` | Tenant defaults | Set tenant-wide defaults (admin only) |
| `models:defaults:write:global` | Global defaults | Set system-wide defaults (admin only) |

---

## 🚫 Why Current Token Fails

### Error Example

```bash
curl -X GET "http://localhost:8000/v1/models/instances" \
  -H "Authorization: Bearer $USER_TOKEN"
```

**Response (403 Forbidden):**
```json
{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "detail": "Insufficient permissions. Required: 'models:read' or 'admin:all'",
  "instance": "/v1/models/instances"
}
```

**Reason**: Token has `user:me tools:invoke:basic` but endpoint requires `models:read` or `admin:all`.

---

## ✅ After Fix

Once you have the correct token:

```bash
# Set new token
export USER_TOKEN="eyJhbGci...NEW_TOKEN_WITH_MODEL_SCOPES"

# Test all endpoints
curl -X GET "http://localhost:8000/v1/models/instances" \
  -H "Authorization: Bearer $USER_TOKEN"
# ✅ 200 OK

curl -X GET "http://localhost:8000/v1/models/defaults" \
  -H "Authorization: Bearer $USER_TOKEN"
# ✅ 200 OK or 404 (both valid)

curl -X POST "http://localhost:8000/v1/models/instances/some-id/tests" \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello"}'
# ✅ 200 OK or 404 (if instance doesn't exist)
```

---

## 📦 Summary

**Problem**: USER_TOKEN missing `models:*` scopes  
**Impact**: All model endpoints return 403 Forbidden  
**Solution**: Request new token with correct scopes  
**Script**: `./get_auth0_tokens_with_model_scopes.sh`  
**Required Scopes**: `user:me tools:invoke:basic models:read models:test models:defaults:read models:defaults:write:self`

---

## 🔗 Related Documentation

- `docs/AUTHENTICATION_FIX_COMPLETE.md` - Auth system implementation
- `docs/ENDPOINT_CONSOLIDATION_COMPLETE.md` - API endpoint organization
- `src/security/model_perms.py` - Permission definitions
- `src/routers/model_instances.py` - Endpoint implementations

---

**Action Required**: Run `./get_auth0_tokens_with_model_scopes.sh` to get properly scoped tokens, then all tests will pass! 🚀
