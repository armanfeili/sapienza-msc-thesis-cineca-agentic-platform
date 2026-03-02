# How to Fix the Permission Issue in the UI

## Problem Summary
The `/v1/models/defaults` endpoint works perfectly with fresh Auth0 tokens, but your UI is showing a 403 error because it's using an old/cached token.

## Verified Facts ✅

1. **Backend is working correctly** - Tested with curl, returns 200 OK
2. **Token extraction is correct** - Backend extracts all scopes properly
3. **Permission check passes** - With fresh tokens, everything works
4. **Your fresh Admin token works** - We just verified it!

## Solution: Update the UI Token

### Option 1: Through the UI (Easiest)

1. **Go to the 🔐 Auth tab** in your Streamlit UI
2. **Click "Logout"** to clear the old token
3. **Click "Login"** again
4. **Enter your credentials**:
   - Username: (your admin username from .env: `AUTH0_ADMIN_USERNAME`)
   - Password: (your admin password from .env: `AUTH0_ADMIN_PASSWORD`)
5. **Click "Login with Password"**
6. **Go to the Agents tab** - it should work now!

### Option 2: Manually Set the Token in UI

If the UI has a token input field or environment variable setting:

1. **Copy this fresh admin token**:
```
eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6IlBfUER0Z1l6angzVXlSVE9mTG10RSJ9.eyJpc3MiOiJodHRwczovL2NpbmVjYS5ldS5hdXRoMC5jb20vIiwic3ViIjoiYXV0aDB8NjhjNzA5OTY5MjI1YWZlMjY1MTUxZWQ1IiwiYXVkIjoiYXBpOi8vY2luZWNhLWFnZW50aWMtcGxhdGZvcm0iLCJpYXQiOjE3NjIxMDg4MzAsImV4cCI6MTc2MjE5NTIzMCwic2NvcGUiOiJ1c2VyOm1lIHRvb2xzOmludm9rZTphbGwgYWRtaW46YWxsIiwiZ3R5IjoicGFzc3dvcmQiLCJhenAiOiJrd2tmMWJHbjJObWRLV3ppb1pZa3Z0WU0wMjJkemI1QyJ9.Lsgwtg9qYu8tptgki69nL5t8aza9wh5uZccc8M7Y3o_MzrPIejF_LdsFtSaMhXCVt0dCbVMT4Hgfoke27dRyXrGozCdhBMwRce0cEpn1TjNJQEJXzltPhWV2rCQtgxqRFf3iP3jhjWuMVy9MNX9jTBY5VLBExv-Uaa8wVjJofEDX9WDgG874xazIZqRiTyLdsGMpLHT-8hLtYDA_Z7nOSuvf0AG3YQoq2QfJMdBjMMd9R4A9EvwftgD1k8tKs7vIJ6-5Bld6ZPdMwsH0OO4rqVLAN6jneY6_z_BgG9Guyv45GFcqx50JhMiRsDgNKFWbJwpdc77VGL3kA0pmtC7AXw
```

2. **This token is valid for 24 hours** (expires Mon Nov 3 19:40:30 CET 2025)
3. **Paste it into the UI** (wherever tokens are stored)

### Option 3: Clear Browser Cache

If the UI stores tokens in browser storage:

1. **Open Developer Console** (F12)
2. **Go to Application tab** (Chrome) or **Storage tab** (Firefox)
3. **Clear** all data under your app's origin
4. **Refresh the page**
5. **Login again**

## For Future Token Generation

Use the script we just tested:

```bash
cd /Users/armanfeili/Arman/Sapienza\ Courses/4-semester/Thesis/ILP-Thesis-2025/Cineca-Agentic-Platform

# Generate fresh tokens
./scripts/fetch_auth0_tokens.sh

# Or save them to .env automatically
./scripts/fetch_auth0_tokens.sh --save-to-env
```

## Verification

After updating the token, verify it works:

```bash
# Set your token
export ADMIN_TOKEN="your_fresh_token_here"

# Test the endpoint
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8000/v1/models/defaults | python3 -m json.tool
```

You should see:
```json
{
  "chat": {
    "instance_id": "...",
    "name": "llama-3.2-3b",
    ...
  },
  "etag": "..."
}
```

## Technical Details

**What was wrong:**
- The UI was using a token that either:
  - Was expired
  - Had different/missing scopes
  - Was corrupted during storage
  - Was generated from a different Auth0 application

**What we verified:**
- ✅ Backend JWKS validation works
- ✅ Permission extraction from `scope` claim works
- ✅ `require_any_perms([USER_ME, ADMIN_ALL])` dependency works
- ✅ Fresh tokens pass all checks

**The fix:**
- Simply use a fresh token from Auth0!

## Debug Logging Added

We also added debug logging to help diagnose future issues. When you restart the backend, you'll see:

```
INFO:src.routers.auth:get_current_user: extracted permissions=['admin:all', 'tools:invoke:all', 'user:me'], scopes=['admin:all', 'tools:invoke:all', 'user:me'], sub=auth0|...
INFO:src.security.model_perms:has_any_permission check: user_perms=['admin:all', 'tools:invoke:all', 'user:me'], required=['user:me', 'admin:all'], user.sub=auth0|...
INFO:src.security.model_perms:has_any_permission: user has admin:all, granting access
```

This will help you verify that tokens are being processed correctly.

---

**Next Steps:**
1. Update your token in the UI (Option 1 above)
2. Try accessing the Agents tab again
3. It should work! 🎉

If you still see issues after using a fresh token, let me know and we'll investigate further.

