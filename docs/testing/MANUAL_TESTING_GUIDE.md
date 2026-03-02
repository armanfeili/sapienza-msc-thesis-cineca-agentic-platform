# Manual Acceptance Testing Guide

**Purpose**: Manual verification checklist for UI and runtime features that can't be fully automated.

**Prerequisites**:
1. Start services: `docker-compose up -d`
2. Access UI: `http://localhost:8501`
3. Have Admin and User tokens ready

---

## ✅ Item 4: Tools Playground

### Steps:
1. Navigate to **Tools** tab in UI
2. Verify tools list loads (not empty, not 404)
3. Click **"Test All Tools"** button (admin only)

### Expected:
- ✅ Per-tool status list appears
- ✅ Most tools succeed (green checkmarks)
- ✅ Failures show clear errors (e.g., "API key required", "Service unavailable")
- ✅ Each result shows: tool name, status, execution time, error details if failed

### Fail If:
- ❌ Button missing or disabled
- ❌ Throws "Resource not found"
- ❌ All tools show identical results
- ❌ Results are empty

###status: ⬜ NOT TESTED | ✅ PASS | ❌ FAIL
**Notes**:

---

## ✅ Item 5: NL → Cypher (Memgraph Path)

### Steps:
1. Navigate to **Graph Explorer** or **NL → Cypher** tab
2. Enter natural language: "Find all nodes"
3. Click **Generate Cypher**
4. Review generated Cypher query
5. Click **Execute**
6. View results table
7. Click **Export to CSV** and **Export to JSON**

### Expected:
- ✅ Generated Cypher appears in code box (not empty)
- ✅ Parameters shown if any (e.g., `{limit: 100}`)
- ✅ Execute button enabled
- ✅ Results table renders with ≥0 rows
- ✅ Columns are properly named
- ✅ Export downloads valid CSV/JSON files
- ✅ Panel auto-disables if Memgraph health is red/amber

### Fail If:
- ❌ Generation returns empty query
- ❌ Execute blocked without clear reason
- ❌ Export buttons do nothing
- ❌ Panel accessible when Memgraph is down

### Status: ⬜ NOT TESTED | ✅ PASS | ❌ FAIL
**Notes**:

---

## ✅ Item 8: Processes / Manifests / DB Ops

### 8a: Processes

#### Steps:
1. Navigate to **Admin → Processes**
2. View list of active processes
3. Click on a process to view details
4. Click **"Stop Process"** on a running process
5. Confirm in modal
6. Check history timeline

#### Expected:
- ✅ Process list shows PID, name, status, uptime
- ✅ Details drawer opens with full info
- ✅ Stop button shows confirmation modal
- ✅ After confirm, process actually stops
- ✅ History timeline shows stop action with timestamp

#### Fail If:
- ❌ Stop button does nothing
- ❌ Process still running after "success" message
- ❌ No confirmation modal

#### Status: ⬜ NOT TESTED | ✅ PASS | ❌ FAIL
**Notes**:

### 8b: Manifests

#### Steps:
1. Navigate to **Admin → Manifests**
2. Click **"Stage New Manifest"**
3. Upload or paste manifest JSON
4. Click **"Preview Staged"**
5. Click **"Activate"**
6. Wait for activation
7. Click **"Rollback to Previous"**
8. View **History** tab

#### Expected:
- ✅ Stage action creates staged manifest
- ✅ Preview shows diff between active and staged
- ✅ Activate promotes staged to active
- ✅ Rollback restores previous version
- ✅ History records each action with timestamp
- ✅ Active and Staged states reconcile correctly

#### Fail If:
- ❌ Any action silently fails
- ❌ UI shows success but state doesn't change
- ❌ History doesn't update

#### Status: ⬜ NOT TESTED | ✅ PASS | ❌ FAIL
**Notes**:

### 8c: DB Operations

#### Steps:
1. Navigate to **Admin → Database → Operations**
2. Create maintenance job (e.g., VACUUM, ANALYZE)
3. View job status
4. Cancel job if still running
5. Check if DB counts are hidden when Memgraph unhealthy

#### Expected:
- ✅ Maintenance job can be created
- ✅ Status shows progress
- ✅ Cancel works and job stops
- ✅ DB counts/operations gated when Memgraph down

#### Fail If:
- ❌ Can't create maintenance job
- ❌ Cancel doesn't stop job
- ❌ DB ops visible when Memgraph unavailable

#### Status: ⬜ NOT TESTED | ✅ PASS | ❌ FAIL
**Notes**:

---

## ✅ Item 9: Providers & Instances

### 9a: Providers

#### Steps:
1. Navigate to **Providers** tab
2. View list of providers
3. Click **"Register New Provider"**
4. Fill in provider details, submit
5. Click **"Set as Default"** on a provider
6. Edit provider (click edit icon)
7. Delete provider (click delete icon)
8. Check banner messages

#### Expected:
- ✅ Provider list loads successfully
- ✅ Can register new provider
- ✅ Set default updates immediately
- ✅ Edit saves changes
- ✅ Delete shows confirmation and removes provider
- ✅ Banners reflect **server** state (not UI-only)

#### Fail If:
- ❌ Any action succeeds in UI but server state unchanged
- ❌ Banner shows "Default: X" but API says otherwise

#### Status: ⬜ NOT TESTED | ✅ PASS | ❌ FAIL
**Notes**:

### 9b: Model Instances

#### Steps:
1. Navigate to **Models → Instances**
2. Click on an instance row
3. Details drawer should open
4. Click **"Test Instance"**
5. Wait for test completion
6. Click **"Delete"** on an instance

#### Expected:
- ✅ Details drawer shows full instance info
- ✅ Test Instance returns real completion or clear error
- ✅ Different models return different test results
- ✅ Delete shows confirmation modal
- ✅ After delete, instance removed from list

#### Fail If:
- ❌ Test Instance always times out
- ❌ All models return identical canned response
- ❌ Delete doesn't remove instance

#### Status: ⬜ NOT TESTED | ✅ PASS | ❌ FAIL
**Notes**:

---

## ✅ Item 10: Explore/Raw Inspector Safety

### Steps:
1. Navigate to **Explore** or **Raw Inspector** tab
2. Enter relative path: `health/live` (without /v1)
3. Click **Execute**
4. Check resolved URL shown in UI
5. Enter full path: `/v1/health/live`
6. Click **Execute**
7. Inspect response panel for sensitive data

#### Expected:
- ✅ UI shows resolved URL (e.g., `/v1/health/live`)
- ✅ Auto-prefixes `/v1` for relative paths
- ✅ Both requests succeed (200 OK)
- ✅ **Never** shows raw Authorization header in response
- ✅ Sensitive headers are redacted or hidden

#### Fail If:
- ❌ 404 due to missing `/v1` prefix
- ❌ Raw `Authorization: Bearer xxx` visible in panel
- ❌ Tokens or secrets shown in response

#### Status: ⬜ NOT TESTED | ✅ PASS | ❌ FAIL
**Notes**:

---

## ✅ Item 11: Error UX & Observability

### Steps:
1. Switch to **User token** (limited scopes)
2. Try to access **Admin → Jobs**
3. Observe error message
4. Check for:
   - HTTP status code
   - Endpoint path
   - Required scopes/permissions
   - Tenant ID
   - Trace ID or Request ID
5. Look for "Retry" button on transient errors

#### Expected:
- ✅ Error shows: HTTP code (e.g., 403)
- ✅ Shows endpoint (e.g., /v1/admin/jobs)
- ✅ Lists required scopes (e.g., "Requires: admin:all")
- ✅ Shows tenant if multi-tenant
- ✅ Includes trace_id or request_id for debugging
- ✅ Retry button for 429, 503, 504 errors
- ✅ Polling has jitter/backoff
- ✅ Polling stops when panel closed

#### Fail If:
- ❌ Generic "Resource not found" with no details
- ❌ No trace_id for error correlation
- ❌ Can't retry transient errors

#### Status: ⬜ NOT TESTED | ✅ PASS | ❌ FAIL
**Notes**:

---

## ✅ Item 12: Role/Permission Guards

### Steps:
1. Log in as **Admin** (token with admin:all scope)
2. Note which actions/buttons are visible
3. Log out and log in as **User** (basic scopes only)
4. Compare available actions
5. Hover over disabled actions

#### Expected:
- ✅ Admin-only actions **hidden or disabled** for User
- ✅ Disabled actions show tooltip: "Requires scope: admin:all"
- ✅ User flows still work (tools list, sessions, etc.)
- ✅ No clickable admin buttons with User token

#### Fail If:
- ❌ Admin actions clickable with User token (should be gated)
- ❌ User gets 403 errors instead of hidden UI
- ❌ No explanation for why action is disabled

#### Status: ⬜ NOT TESTED | ✅ PASS | ❌ FAIL
**Notes**:

---

## ✅ Item 13: Auth Lifecycle

### Steps:
1. Log in as Admin
2. Check token expiry countdown
3. Let token approach T-5min (or set short TTL for testing)
4. Observe auto-renewal
5. Navigate to **Auth → Me**
6. View claims, roles, scopes
7. Check server logs for token masking

#### Expected:
- ✅ Token countdown visible in UI
- ✅ Auto-renewal at T-5min (token refreshes)
- ✅ `/auth/me` shows:
  - Username/sub
  - Scopes (array)
  - Roles (array)
  - Tenant ID
- ✅ Server logs show `Bearer [REDACTED]`, not full token

#### Fail If:
- ❌ Token expires mid-session without renewal
- ❌ Logs show full `Bearer eyJhbG...` tokens
- ❌ /auth/me missing critical claims

#### Status: ⬜ NOT TESTED | ✅ PASS | ❌ FAIL
**Notes**:

---

## ✅ Item 14: Developer Mode Hygiene

### Steps:
1. Check default UI state (Developer Mode OFF)
2. Look for internal/debug endpoints in navigation
3. Toggle **Developer Mode** ON
4. Check which new options appear
5. Try to execute destructive operation

#### Expected:
- ✅ Internal/DEBUG endpoints **hidden by default**
- ✅ Only appear when Developer Mode toggled ON
- ✅ Destructive ops require confirmation modal
- ✅ Developer Mode setting persists per session

#### Fail If:
- ❌ Internal endpoints visible by default
- ❌ Can execute destructive ops without confirmation
- ❌ No clear indication of Developer Mode status

#### Status: ⬜ NOT TESTED | ✅ PASS | ❌ FAIL
**Notes**:

---

## ✅ Item 15: Security & Secrets

### Steps:
1. Search codebase for hardcoded secrets:
   ```bash
   grep -r "sk-" ui/ src/ --include="*.py"
   grep -r "password.*=.*['\"]" ui/ src/ --include="*.py"
   ```
2. Check `.streamlit/secrets.toml` is in `.gitignore`
3. Review CORS configuration in `src/app.py`
4. Verify client secrets use env vars or secrets.toml
5. Check if any credentials were previously committed (git history)

#### Expected:
- ✅ No hardcoded API keys, passwords, tokens in code
- ✅ `.streamlit/secrets.toml` in `.gitignore`
- ✅ CORS properly configured (not `allow_origins=["*"]` in production)
- ✅ All secrets loaded from environment or secrets file
- ✅ Any previously exposed credentials rotated

#### Fail If:
- ❌ Secrets in code, logs, or UI
- ❌ `.streamlit/secrets.toml` tracked by git
- ❌ CORS allows all origins in production

#### Status: ⬜ NOT TESTED | ✅ PASS | ❌ FAIL
**Notes**:

---

## ✅ Item 16: Docs Completeness

### Steps:
1. Read main **README.md**
2. Check for 5-minute deployment section
3. Find **docs/INDEX.md**
4. Open **OPERATOR_RUNBOOK.md**
5. Look for troubleshooting section
6. Verify scenarios match real issues

#### Expected:
- ✅ README has "Quick Start - 5-Minute Deployment"
- ✅ `docs/INDEX.md` exists with categorized docs
- ✅ `OPERATOR_RUNBOOK.md` covers:
  - Provider unreachable → how to fix
  - Memgraph down → how to restart
  - Defaults missing → how to set
  - Common 404/403 errors → how to debug
- ✅ Troubleshooting matches real failure modes

#### Fail If:
- ❌ README claims success scenarios you can't reproduce
- ❌ Docs missing common failure modes
- ❌ No operator runbook

#### Status: ⬜ NOT TESTED | ✅ PASS | ❌ FAIL
**Notes**:

---

## 🎯 "DONE SCENARIO" - Complete E2E Test

### As Admin, in the UI:

1. **Type**: "List available tools."
2. **Watch**: Real agent run with:
   - Non-null `model` and/or `manager`
   - Multiple tool steps visible
   - Concrete outputs (not placeholders)
   - Timestamps and durations
3. **Ask**: Natural language graph question
4. **See**: Generated Cypher query
5. **Execute**: Get rows back
6. **Export**: Download CSV successfully
7. **Verify**:
   - All health cards green
   - No 404s caused by UI
   - Errors (when induced) are actionable with trace_id
   - Tokens are masked in logs

#### Status: ⬜ NOT TESTED | ✅ PASS | ❌ FAIL
**Notes**:

---

## Summary Checklist

- [ ] Item 1: Platform Health ✅ (Automated test)
- [ ] Item 2: Defaults Set ✅ (Automated test)
- [ ] Item 3: Agent Run Real ✅ (Automated test)
- [ ] Item 4: Tools Playground ⬜ (Manual)
- [ ] Item 5: NL → Cypher ⬜ (Manual)
- [ ] Item 6: Sessions ✅ (Automated test)
- [ ] Item 7: Jobs ✅ (Automated test)
- [ ] Item 8: Processes/Manifests ⬜ (Manual)
- [ ] Item 9: Providers/Instances ⬜ (Manual)
- [ ] Item 10: Explorer Safety ✅ (Automated test)
- [ ] Item 11: Error UX ✅ (Automated test)
- [ ] Item 12: Role Guards ✅ (Automated test)
- [ ] Item 13: Auth Lifecycle ✅ (Automated test)
- [ ] Item 14: Developer Mode ⬜ (Manual)
- [ ] Item 15: Security/Secrets ⬜ (Manual)
- [ ] Item 16: Docs Completeness ⬜ (Manual)

**Automated**: 9/16 items  
**Manual**: 7/16 items

---

## Next Steps

1. Run automated tests:
   ```bash
   pytest tests/acceptance/test_acceptance_checklist.py -v
   ```

2. Complete manual tests using this guide

3. Document any failures

4. Fix issues and re-test

5. Sign off when all ✅
