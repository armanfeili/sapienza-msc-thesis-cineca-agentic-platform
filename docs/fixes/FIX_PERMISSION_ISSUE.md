# Fix Permission Issue - Step-by-Step Guide

## Problem
Getting `403 Forbidden` error on `/v1/models/defaults` even though the token has the correct scopes.

## Solution Steps

### Step 1: Make Sure Backend is Running with Debug Logging

Open a terminal and run:

```bash
cd /Users/armanfeili/Arman/Sapienza\ Courses/4-semester/Thesis/ILP-Thesis-2025/Cineca-Agentic-Platform

# Start backend with INFO-level logging
uvicorn src.app:app --reload --log-level=info --port 8000
```

**Important**: Keep this terminal open and watch the logs!

### Step 2: Run the Comprehensive Diagnostic Test

Open a **NEW** terminal and run:

```bash
cd /Users/armanfeili/Arman/Sapienza\ Courses/4-semester/Thesis/ILP-Thesis-2025/Cineca-Agentic-Platform

# Run the test script
./test_permission_fix.sh
```

This script will:
1. ✅ Fetch a fresh admin token from Auth0
2. ✅ Decode it and show all claims
3. ✅ Test `/v1/auth/me` to verify the token is valid
4. ✅ Test `/v1/models/defaults` to reproduce the issue
5. ✅ Show you exactly what's happening

### Step 3: Check the Backend Logs

While the test is running, look at the **first terminal** (where the backend is running).

You should see lines like:

```
INFO:src.routers.auth:get_current_user: extracted permissions=['admin:all', 'tools:invoke:all', 'user:me'], scopes=['admin:all', 'tools:invoke:all', 'user:me'], sub=auth0|68c709969225afe265151ed5
INFO:src.security.model_perms:has_any_permission check: user_perms=['admin:all', 'tools:invoke:all', 'user:me'], required=['user:me', 'admin:all'], user.sub=auth0|68c709969225afe265151ed5
INFO:src.security.model_perms:has_any_permission: user has admin:all, granting access
```

### Step 4: Analyze the Results

#### ✅ If the test script shows **SUCCESS** (404 or 200):
- The issue is fixed!
- 404 means no default model is configured yet (go to Models tab to set one)
- 200 means everything is working perfectly

#### ❌ If the test script shows **403 Forbidden**:

Check what the logs say:

**Case A: Permissions list is EMPTY**
```
INFO:src.routers.auth:get_current_user: extracted permissions=[], scopes=[], sub=...
```

**Problem**: Token claims are not being extracted
**Cause**: Token format doesn't match what the backend expects

**Fix**: Run this to see the token structure:
```bash
python3 debug_token.py "$AUTH0_ADMIN_TOKEN"
```

Then tell me what the output shows, especially:
- What does `scope` claim contain?
- What does `permissions` claim contain?
- Is it a string or array?

**Case B: Permissions are extracted but check fails**
```
INFO:src.routers.auth:get_current_user: extracted permissions=['admin:all', 'tools:invoke:all', 'user:me'], ...
INFO:src.security.model_perms:has_any_permission check: user_perms=[], required=['user:me', 'admin:all'], ...
```

**Problem**: Permissions are extracted but not passed to the checker
**Cause**: Bug in the dependency chain

**Fix**: I'll need to patch the code (send me these logs)

### Step 5: Update UI Token

After the backend fix is confirmed working:

1. Go to the **🔐 Auth** tab in the UI
2. Click **Logout**
3. Click **Login** to get a fresh token
4. Go to **🤖 Agents** tab
5. The error should be gone!

## Quick Manual Test

If you want to test manually without the script:

```bash
# 1. Get your token from the UI or generate one
./scripts/fetch_auth0_tokens.sh

# The script will output export commands, copy them:
export AUTH0_ADMIN_TOKEN='your_token_here'

# 2. Test the endpoint directly
curl -v -X GET "http://localhost:8000/v1/models/defaults" \
  -H "Authorization: Bearer $AUTH0_ADMIN_TOKEN" \
  -H "Content-Type: application/json"

# 3. Check what the backend extracted
curl -X GET "http://localhost:8000/v1/auth/me" \
  -H "Authorization: Bearer $AUTH0_ADMIN_TOKEN" | jq
```

## Expected Output

### ✅ Success (404 - No defaults configured yet)
```json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "No default model configured",
  "instance": "/v1/models/defaults"
}
```

This is actually **GOOD**! It means:
- ✅ Token is valid
- ✅ Permission check passed
- ⚠️ You just need to set a default model (go to Models tab)

### ✅ Success (200 - Defaults are configured)
```json
{
  "chat": {
    "instance_id": "...",
    "name": "llama-3.2-3b",
    "provider_id": "ollama-local",
    "model_id": "llama3.2:3b-instruct"
  },
  "etag": "..."
}
```

### ❌ Failure (403 - Permission denied)
```json
{
  "detail": "Insufficient permissions. Required: 'user:me' or 'admin:all'"
}
```

If you see this, check the backend logs and share them with me.

## Need Help?

Run the test script and share:
1. The complete output from `./test_permission_fix.sh`
2. The backend logs from when you ran the test
3. I'll identify the exact issue and provide a fix

## Files Created

- `debug_token.py` - Decodes JWT tokens to inspect claims
- `test_permission_fix.sh` - Comprehensive diagnostic test
- `scripts/fetch_auth0_tokens.sh` - Already existed, generates tokens

