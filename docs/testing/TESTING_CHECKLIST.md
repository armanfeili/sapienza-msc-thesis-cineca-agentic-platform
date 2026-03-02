# 🧪 Testing Checklist

Manual testing checklist for the Streamlit UI implementation.

## ✅ Authentication Testing

### Login/Logout Flow
- [ ] Click "Login Admin" - should fetch token and show green badge
- [ ] Click "Login User" - should fetch token and show green badge
- [ ] Machine token auto-fetches on app start
- [ ] Token badges show correct subject and scopes
- [ ] Token countdown shows time until expiry
- [ ] "Logout Admin" clears admin token
- [ ] "Logout User" clears user token
- [ ] Identity selector shows only active identities
- [ ] Switching identity updates active token

### Claims Display
- [ ] `/auth/me` shows user claims when logged in
- [ ] Scopes displayed as chips
- [ ] Expiry status shown correctly
- [ ] Error shown when not logged in

### Permission Tests
- [ ] "Test User Access" works with valid token
- [ ] "Test Admin Access" requires admin scopes
- [ ] Appropriate error messages for 401/403

## ✅ Dashboard Testing

### Health Endpoints
- [ ] "Liveness" card shows status
- [ ] "Readiness" card shows status
- [ ] "Startup" card shows status
- [ ] Component cards show for Memgraph, Postgres, Redis
- [ ] Latency displayed in milliseconds
- [ ] "Refresh Now" updates all cards
- [ ] Auto-refresh toggle works (wait 30s)

## ✅ Explore Testing

### API Root
- [ ] "Fetch Root Info" shows API name and version
- [ ] Response drawer displays full JSON

### OpenAPI Spec
- [ ] "View OpenAPI Spec" fetches and displays spec
- [ ] Endpoint count shown correctly
- [ ] "Download Spec" button works
- [ ] Downloaded JSON is valid

### Raw Inspector
- [ ] Can send GET requests
- [ ] Can send POST requests with body
- [ ] Response shown in drawer
- [ ] Errors displayed clearly

## ✅ Agents Testing

### Agent Runs (Copilot-style)
- [ ] Prompt input accepts text
- [ ] Model/tenant optional fields work
- [ ] "Run Agent" creates a run
- [ ] Run ID displayed
- [ ] Status updates (running → completed)
- [ ] Answer displayed prominently at top
- [ ] Timeline shows all steps/tool calls
- [ ] Tool call inputs/outputs shown
- [ ] Durations displayed
- [ ] "Refresh" updates status
- [ ] "Copy Answer" shows answer text
- [ ] "Export JSON" shows full trace
- [ ] Polling stops when terminal state reached

### Sessions
- [ ] "Create New Session" works
- [ ] Session name and metadata optional
- [ ] "Refresh Sessions" updates list
- [ ] Session table displays with export
- [ ] "View Session" shows details
- [ ] Session detail drawer displays correctly

## ✅ Jobs Testing

### User Jobs
- [ ] "Create New Job" form accepts parameters
- [ ] JSON parameters validated
- [ ] Idempotency key optional
- [ ] Job created successfully
- [ ] Jobs list with filters
- [ ] Status filter works (all/pending/running/completed/failed)
- [ ] Pagination works
- [ ] "View Status" shows job details
- [ ] Progress and status metrics shown
- [ ] "View Events" fetches events
- [ ] Events displayed with timestamps
- [ ] Last Event ID shown for resume
- [ ] Resume from last event works
- [ ] "Cancel Job" cancels successfully

### Admin Jobs (requires admin scope)
- [ ] Admin jobs tab visible only with admin scope
- [ ] Admin jobs list displays
- [ ] Table export works

## ✅ Tools Testing

### Discovery
- [ ] "Refresh Tools" updates list
- [ ] Tool cards show name, description, capabilities
- [ ] Safe/Admin indicator shown
- [ ] "View Schema" displays schema drawer
- [ ] Schema cached for performance

### Invocation
- [ ] Tool name input accepted
- [ ] Parameters schema displayed
- [ ] Parameters JSON validated
- [ ] "Invoke Tool" creates invocation
- [ ] Execution ID returned
- [ ] Result fetched automatically

### NL→Cypher Special Case
- [ ] Generated Cypher query displayed
- [ ] Parameters shown
- [ ] Memgraph results shown as table
- [ ] Row count displayed
- [ ] Read-only enforcement indicator
- [ ] Row limit shown
- [ ] "Export CSV" works
- [ ] "Export JSON" works
- [ ] Unsafe query reason shown if blocked

## ✅ Models Testing

### Model Instances
- [ ] Current defaults displayed
- [ ] "Refresh Instances" updates list
- [ ] Provider filter works
- [ ] Status filter works
- [ ] Instance table displays
- [ ] "View Details" shows instance info
- [ ] Metrics shown (provider, status, health)
- [ ] "Test Instance" accepts prompt
- [ ] Test results show latency, tokens, output
- [ ] "Delete" removes instance (with confirmation if implemented)

### Providers (Admin Only)
- [ ] Main provider displayed
- [ ] Main provider health shown
- [ ] "Register New Provider" form accepts data
- [ ] Provider type dropdown works
- [ ] Configuration JSON validated
- [ ] Provider registered successfully
- [ ] "Refresh Providers" updates list
- [ ] Provider table displays

## ✅ Tenants Testing (Admin Only)

### CRUD Operations
- [ ] "Create New Tenant" form works
- [ ] Tenant name required
- [ ] Status dropdown (active/inactive)
- [ ] Metadata JSON optional and validated
- [ ] Tenant created successfully
- [ ] "Refresh Tenants" updates list
- [ ] Pagination works (page, size)
- [ ] Tenant table displays
- [ ] "View Details" shows tenant info
- [ ] Metrics shown (ID, status, created_at)
- [ ] "Update" shows edit form
- [ ] Update saves changes
- [ ] "Delete" requires confirmation
- [ ] Delete removes tenant

## ✅ Admin Testing (Admin Only)

### Processes
- [ ] "Refresh Processes" updates list
- [ ] Process table displays
- [ ] PID input accepted
- [ ] "Stop Process" stops process
- [ ] "Manifest History" fetches history
- [ ] "Process History" fetches history
- [ ] Histories shown in drawers

### Built-in Manifests
- [ ] "Refresh Manifests" updates
- [ ] Staged manifests listed
- [ ] Active manifests listed
- [ ] "Stage Manifest" accepts name/version
- [ ] Staging works
- [ ] "Activate Manifest" activates
- [ ] "Rollback Manifest" rolls back
- [ ] "View Manifest History" shows timeline

### Ops
- [ ] "Preview Staged Manifests" fetches preview
- [ ] Preview shown in drawer
- [ ] Auto-start override checkbox works
- [ ] "Apply Override" applies setting

### Database
- [ ] "View DB Counts" fetches counts
- [ ] Counts shown as metrics
- [ ] Full counts in drawer
- [ ] Job type dropdown works
- [ ] Parameters JSON optional
- [ ] "Create DB Job" creates job
- [ ] Job ID returned
- [ ] "View Job Status" shows details
- [ ] "Cancel Job" cancels

### Internal (Developer Mode)
- [ ] Internal tab only visible with Developer Mode ON
- [ ] Warning message displayed
- [ ] Instructions shown

## ✅ Cross-Cutting Features

### Token Management
- [ ] Tokens masked in logs (first 8 + last 8 chars)
- [ ] Tokens never shown in full in UI
- [ ] Expired tokens trigger re-login prompt
- [ ] Token renewal works when < 5 min to expiry

### Tables
- [ ] Column chooser works
- [ ] Export CSV works
- [ ] Export JSON works
- [ ] Copy button shows data

### JSON Drawers
- [ ] Sensitive fields sanitized (tokens, secrets, passwords)
- [ ] "Copy JSON" works
- [ ] "Copy cURL" works (when applicable)

### Error Handling
- [ ] 401 errors show "Please log in"
- [ ] 403 errors show required scopes
- [ ] 404 errors show "Not found"
- [ ] 429 errors show retry time
- [ ] 5xx errors show "Service unavailable"
- [ ] Errors added to error log with trace ID

### Logging
- [ ] Logs written to `logs/ui.log`
- [ ] Tokens masked in log entries
- [ ] Log pane shows recent entries
- [ ] Filter by keyword works
- [ ] Show all lines toggle works

### UI/UX
- [ ] Developer mode toggle works
- [ ] Identity selector updates correctly
- [ ] Token badges update on login/logout
- [ ] Tabs render without errors
- [ ] Tables responsive
- [ ] Forms validate input
- [ ] Spinners show during loading
- [ ] Success/error toasts display
- [ ] Metrics formatted nicely
- [ ] Timestamps human-readable

## ✅ Performance & Polish

### Caching
- [ ] Tool schemas cached (don't refetch on every invoke)
- [ ] Tenant list cached with manual refresh
- [ ] Provider list cached with manual refresh

### Polling
- [ ] Agent runs poll until completion
- [ ] Polling stops at terminal state
- [ ] Backoff/jitter prevents API overload

### Exports
- [ ] CSV exports valid
- [ ] JSON exports valid
- [ ] Downloads have sensible filenames

## ✅ Security

### Scope Enforcement
- [ ] Admin features hidden without `admin:all`
- [ ] Tool invocation limited without `tools:invoke:all`
- [ ] Disabled controls show tooltip with required scopes

### Data Sanitization
- [ ] No tokens in JSON displays
- [ ] No secrets in JSON displays
- [ ] No passwords in JSON displays
- [ ] Masked values show as `***` or `xxx...xxx`

### Dangerous Actions
- [ ] Delete operations require confirmation
- [ ] Internal endpoints require Developer Mode
- [ ] Clear warnings for destructive actions

## 📝 Testing Notes

Record any issues found during testing:

```
Date: ___________
Tester: ___________

Issues Found:
1. _________________________________
2. _________________________________
3. _________________________________

Suggestions:
1. _________________________________
2. _________________________________
```

## ✅ Final Checklist

- [ ] All tabs load without errors
- [ ] All auth flows work
- [ ] All API endpoints reachable
- [ ] All permissions enforced correctly
- [ ] All exports work
- [ ] All logs are clean (no exceptions)
- [ ] All tokens masked properly
- [ ] UI responsive and fast
- [ ] Documentation complete and accurate

**Sign-off**: _________________ Date: _____________
