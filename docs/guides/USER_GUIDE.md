# Cineca Agentic Platform - User Guide

**Version:** 1.0  
**Last Updated:** November 2, 2025  
**For:** End Users and Administrators

---

## 📚 Table of Contents

1. [Getting Started](#getting-started)
2. [Authentication](#authentication)
3. [Model Management](#model-management)
4. [Creating Agent Runs](#creating-agent-runs)
5. [Using Agent Sessions](#using-agent-sessions)
6. [Managing Jobs](#managing-jobs)
7. [Tool Invocation](#tool-invocation)
8. [Batch Operations](#batch-operations)
9. [Export & Import](#export--import)
10. [Tenant Management](#tenant-management)
11. [Admin Features](#admin-features)
12. [Troubleshooting](#troubleshooting)

---

## 🚀 Getting Started

### Prerequisites

- Modern web browser (Chrome, Firefox, Safari, Edge)
- Auth0 credentials (username and password)
- Access to the platform URL (default: http://localhost:8501)

### First Time Setup

1. **Access the Platform**
   - Navigate to the platform URL in your browser
   - You'll see the Cineca Agentic Platform homepage

2. **Login**
   - Go to the **🔐 Auth** tab
   - Enter your username and password
   - Click "Login"
   - Your token will be displayed and automatically used

3. **Check System Status**
   - Look at the sidebar for token status
   - Green = healthy, yellow = expiring soon, red = expired
   - Check the **📊 Dashboard** tab for system health

---

## 🔐 Authentication

### Identity Types

The platform supports three identity types:

| Identity | Purpose | Scopes |
|----------|---------|--------|
| **Admin** | Full platform access | `user:me`, `admin:all`, `tools:invoke:all` |
| **User** | Regular user operations | `user:me` |
| **Machine** | Service-to-service | `internal:all` |

### Logging In

**Step 1:** Navigate to the **🔐 Auth** tab

**Step 2:** Select your identity type (Admin/User/Machine)

**Step 3:** Enter credentials:
- **Admin/User**: Username and Password
- **Machine**: Client ID and Client Secret

**Step 4:** Click the login button

**Step 5:** Verify token appears in the sidebar

### Managing Tokens

**View Token Info:**
- Token badges show in the top-left
- Click on a badge to see full details
- Sidebar shows time until expiry

**Token Expiring Soon:**
- Yellow warning appears at 5 minutes before expiry
- Auto-renewal happens automatically for machine tokens
- Manual renewal: Go to Auth tab and login again

**Token Expired:**
- Red error shown in sidebar
- Return to Auth tab and login again
- Use "Clear Cache" button if errors persist

---

## 🧠 Model Management

### Registering a Model Provider

**Step 1:** Go to **🧠 Models** tab → **Model Providers** sub-tab

**Step 2:** Click "➕ Register New Provider"

**Step 3:** Fill in provider details:
- **Provider ID**: Unique identifier (e.g., `ollama-local`)
- **Provider Type**: Select from dropdown (OpenAI, Ollama, Azure, etc.)
- **Base URL**: API endpoint (e.g., `http://ollama:11434`)
- **API Key**: If required by provider

**Step 4:** Click "Register Provider"

**Step 5:** Set as default (optional): Check "Set as default provider"

### Creating a Model Instance

**Step 1:** Go to **Model Instances** sub-tab

**Step 2:** Click "➕ Create Model Instance"

**Step 3:** Configure model:
- **Model Name**: Name in provider (e.g., `llama3.1:latest`)
- **Instance Name**: Display name (e.g., `My Llama Model`)
- **Provider**: Select from dropdown
- **Enabled**: Check to make available immediately

**Step 4:** Click "Create Instance"

**Step 5:** Instance automatically becomes your default (first time)

### Setting Default Models

**Global Default** (Admins only):
- Affects all users in tenant
- Set in Model Defaults section

**User Default**:
- Personal default model
- Overrides global default
- First model you create becomes default automatically

---

## 🤖 Creating Agent Runs

Agent runs are one-shot AI tasks that execute and return results.

### Basic Agent Run

**Step 1:** Go to **🤖 Agents** tab → **Agent Runs** sub-tab

**Step 2:** Fill in the form:
```
Prompt: "Analyze the sentiment of this text: I love this product!"
Max Iterations: 5
```

**Step 3:** Click "🚀 Create Agent Run"

**Step 4:** Watch real-time progress in the timeline

**Step 5:** View result when complete

### Advanced Options

**Temperature:**
- Range: 0.0 to 1.0
- Lower = more deterministic
- Higher = more creative

**Max Tokens:**
- Maximum response length
- Default: 1000

**Tools:**
- Select tools agent can use
- Examples: web_search, calculator, file_reader

### Monitoring Progress

**Timeline View:**
- Shows each iteration
- Tool calls displayed
- Errors highlighted

**Status Indicators:**
- 🟡 Running
- ✅ Completed
- ❌ Failed
- 🚫 Cancelled

### Viewing Results

**Answer Section:**
- Final agent response
- Formatted for readability

**Full Details:**
- Click "🔍 View Full Details"
- Shows complete JSON
- Includes all iterations and tool calls

---

## 💬 Using Agent Sessions

Sessions enable multi-turn conversations with AI agents.

### Creating a Session

**Step 1:** Go to **🤖 Agents** tab → **Agent Sessions** sub-tab

**Step 2:** Click "➕ Create New Session"

**Step 3:** Fill in details:
```
Session Name: Customer Support Chat
Description: Help desk conversation
Metadata: {"department": "support", "priority": "high"}
```

**Step 4:** Click "Create Session"

### Sending Messages

**Step 1:** Select session from dropdown

**Step 2:** Type message in text area:
```
Hello, I need help with my account settings
```

**Step 3:** Click "📨 Send Message"

**Step 4:** View response in conversation history

### Session Features

**Conversation History:**
- All messages displayed chronologically
- User messages: blue background
- Agent responses: gray background

**Session Steps:**
- View all processing steps
- See tool invocations
- Debug agent reasoning

**Export Session:**
- Download as JSON
- Share with team
- Archive for later

---

## 📋 Managing Jobs

Jobs are background tasks that run asynchronously.

### Creating a Job

**Step 1:** Go to **📋 Jobs** tab

**Step 2:** Click "➕ Create New Job"

**Step 3:** Configure job:
```
Job Type: data_processing
Parameters: {
  "input_file": "data.csv",
  "output_format": "json"
}
Priority: normal
Idempotency Key: optional-unique-id
```

**Step 4:** Click "🚀 Create Job"

### Monitoring Jobs

**Job List:**
- Filter by status (pending, running, completed, failed)
- Filter by type
- Pagination controls

**Job Details:**
- Click on job ID
- View progress
- See events timeline

**Job Events:**
- Real-time event streaming
- Status changes
- Error messages
- Completion notifications

### Cancelling Jobs

**Step 1:** Find job in list

**Step 2:** Click job ID to expand details

**Step 3:** Click "🚫 Cancel Job"

**Step 4:** Confirm cancellation

---

## 🔧 Tool Invocation

Tools extend agent capabilities with external functions.

### Available Tools

**Built-in Tools:**
- `web_search` - Search the internet
- `calculator` - Mathematical calculations
- `file_reader` - Read file contents
- `api_caller` - Call external APIs

### Invoking a Tool Directly

**Step 1:** Go to **🔧 Tools** tab

**Step 2:** Select tool from list

**Step 3:** Fill in parameters:
```
Tool: calculator
Parameters: {
  "expression": "25 * 4 + 10"
}
```

**Step 4:** Click "▶️ Invoke Tool"

**Step 5:** View result

### Tool Configuration

**Admins** can:
- Register custom tools
- Update tool schemas
- Enable/disable tools
- Set permissions

---

## 📦 Batch Operations

Batch operations allow you to perform multiple create, update, or delete operations in a single API request for improved efficiency.

### Generic Batch Operations

Execute up to 100 operations in a single request across different resource types.

**Endpoint:** `POST /v1/batch/operations`

**Example Request:**
```json
{
  "operations": [
    {
      "operation": "create",
      "resourceType": "model",
      "data": {
        "instanceId": "model-1",
        "modelName": "gpt-4-turbo",
        "providerId": "openai-prod"
      }
    },
    {
      "operation": "delete",
      "resourceType": "tool",
      "resourceId": "old-tool-id"
    }
  ],
  "continueOnError": true
}
```

**Response:**
```json
{
  "totalOperations": 2,
  "successCount": 1,
  "failureCount": 1,
  "results": [
    {
      "operation": "create",
      "resourceType": "model",
      "resourceId": "model-1",
      "success": true,
      "statusCode": 201,
      "message": "Model created"
    },
    {
      "operation": "delete",
      "resourceType": "tool",
      "resourceId": "old-tool-id",
      "success": false,
      "statusCode": 404,
      "error": "Tool not found"
    }
  ]
}
```

### Bulk Create Models

Create multiple model instances at once for a tenant.

**Endpoint:** `POST /v1/batch/models/bulk-create?tenant_id={tenant_id}`

**Example:**
```json
[
  {
    "instanceId": "model-1",
    "modelName": "gpt-4-turbo",
    "providerId": "openai-prod"
  },
  {
    "instanceId": "model-2",
    "modelName": "claude-3-opus",
    "providerId": "anthropic-prod"
  }
]
```

**Limits:**
- Maximum 50 models per request
- Each model must have unique `instanceId`
- All models created for the same tenant

### Bulk Delete Models

Delete multiple model instances in one request.

**Endpoint:** `DELETE /v1/batch/models/bulk-delete?tenant_id={tenant_id}`

**Example:**
```json
["model-1", "model-2", "model-3"]
```

### Bulk Create Tools

Register multiple tools simultaneously.

**Endpoint:** `POST /v1/batch/tools/bulk-create?tenant_id={tenant_id}`

**Best Practices:**
- ✅ Use `continueOnError: true` to process all operations even if some fail
- ✅ Keep batch size under 50 for optimal performance
- ✅ Review batch results to identify failures
- ❌ Don't exceed 100 operations per batch
- ❌ Don't create duplicate resource IDs

---

## 💾 Export & Import

Export and import platform configurations for backup, migration, or disaster recovery.

### Exporting Configurations

Export all or specific resource types to JSON or ZIP format.

**Endpoint:** `POST /v1/export/`

**Example Request:**
```json
{
  "resources": ["tenants", "models", "providers", "tools", "agents"],
  "format": "json",
  "includeSecrets": false
}
```

**Response:**
```json
{
  "metadata": {
    "exportedAt": "2025-11-02T22:40:00Z",
    "exportedBy": "admin@example.com",
    "platformVersion": "1.0.0",
    "itemCount": 42,
    "format": "json"
  },
  "tenants": [...],
  "models": [...],
  "providers": [...],
  "tools": [...],
  "agents": [...]
}
```

### Export Specific Tenant

Export configuration for a single tenant only.

**Endpoint:** `POST /v1/export/tenant/{tenant_id}`

**Example:**
```bash
curl -X POST http://localhost:8000/v1/export/tenant/my-tenant \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"format": "zip"}' \
  -o tenant-backup.zip
```

### Importing Configurations

Restore configurations from an export file.

**Endpoint:** `POST /v1/export/import`

**Example Request:**
```json
{
  "data": {
    "metadata": {...},
    "tenants": [...],
    "models": [...]
  },
  "validate": true,
  "conflictResolution": "skip"
}
```

**Conflict Resolution Options:**
- `skip` - Skip resources that already exist (default)
- `overwrite` - Replace existing resources with imported data
- `rename` - Auto-rename imported resources to avoid conflicts

**Best Practices:**
- ✅ Always validate imports before applying (`validate: true`)
- ✅ Export regularly for disaster recovery
- ✅ Use ZIP format for large exports
- ✅ Store exports in secure, versioned storage
- ❌ Don't include secrets in exports unless absolutely necessary
- ❌ Don't import untrusted export files

**Security Notes:**
- Exported secrets are encrypted by default
- Use `includeSecrets: false` to exclude all credentials
- Import validates schema and resource references
- Failed validations prevent any changes

---

## 🏢 Tenant Management

Tenants provide multi-tenancy isolation.

### Viewing Tenants

**Step 1:** Go to **🏢 Tenants** tab

**Step 2:** View all tenants you have access to

**Step 3:** Click tenant ID to see details

### Creating a Tenant (Admin Only)

**Step 1:** Click "➕ Create New Tenant"

**Step 2:** Fill in details:
```
Tenant Name: Acme Corp
Admin Name: John Doe
Admin Email: john@acme.com
Description: Main production tenant
```

**Step 3:** Click "Create Tenant"

### Switching Tenants

**Method 1:** Use tenant selector in top bar

**Method 2:** Go to Tenants tab and click "Switch to this tenant"

---

## ⚙️ Admin Features

### Process Management

**View Processes:**
- See all running processes
- CPU and memory usage
- Stop/restart processes

### Manifest Management

**Stage Manifests:**
- Upload new configurations
- Version control

**Activate Manifests:**
- Deploy to production
- Rollback if needed

### Database Operations

**View Stats:**
- Table counts
- Size metrics

**Create Jobs:**
- Database maintenance
- Cleanup tasks

---

## 🔧 Troubleshooting

### Common Issues

#### "No Model Defaults Configured"

**Cause:** No default model set for your user/tenant

**Solution:**
1. Go to **🧠 Models** tab
2. Create a model instance (auto-becomes default)
3. Or manually set default in "Model Defaults" section

#### "403 Forbidden" Error

**Cause:** Missing required permissions or cached error

**Solutions:**
1. Check token scopes in sidebar
2. Click "🔄 Clear All Cache" in sidebar
3. Re-login in Auth tab
4. Contact admin if permissions are wrong

#### Token Expired

**Cause:** Token lifetime exceeded (24 hours)

**Solution:**
1. Go to **🔐 Auth** tab
2. Login again with same credentials
3. New token will be issued

#### Stuck Permission Errors

**Cause:** Session state caching

**Solution:**
1. Click "🔄 Clear All Cache" in sidebar
2. Hard refresh browser (Cmd+Shift+R or Ctrl+Shift+R)
3. Re-login if needed

#### Slow Performance

**Causes:**
- Large datasets
- Network issues
- High load

**Solutions:**
1. Use pagination for large lists
2. Filter results to reduce data
3. Check network connection
4. Contact admin if persistent

### Getting Help

**Self-Service:**
1. Check sidebar for system status
2. Review error messages carefully
3. Try "Clear Cache" button
4. Use retry buttons on error screens

**Contact Support:**
- Email: support@cineca-platform.com
- Include: Error message, screenshot, steps to reproduce

---

## 💡 Best Practices

### Token Management

- ✅ Renew tokens before they expire
- ✅ Use machine tokens for automation
- ✅ Keep credentials secure
- ❌ Don't share tokens between users

### Model Configuration

- ✅ Set descriptive instance names
- ✅ Test models before production use
- ✅ Monitor model performance
- ❌ Don't use experimental models in production

### Agent Runs

- ✅ Provide clear, specific prompts
- ✅ Set reasonable max iterations (3-10)
- ✅ Review results before taking action
- ❌ Don't run infinite loops

### Jobs

- ✅ Use idempotency keys for critical jobs
- ✅ Monitor job progress
- ✅ Set appropriate priorities
- ❌ Don't create duplicate jobs

---

## 🎯 Quick Reference

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Cmd/Ctrl + R` | Refresh page |
| `Cmd/Ctrl + Shift + R` | Hard refresh |
| `Esc` | Close modals |

### Status Icons

| Icon | Meaning |
|------|---------|
| 🟢 ✅ | Success / Healthy |
| 🟡 ⏱️ | Warning / Pending |
| 🔴 ❌ | Error / Failed |
| 🔵 ℹ️ | Info |
| 🟣 🔄 | Running / In Progress |

### Scope Reference

| Scope | Permission |
|-------|------------|
| `user:me` | Access own resources |
| `admin:all` | Full admin access |
| `tools:invoke:all` | Invoke any tool |
| `internal:all` | System operations |

---

## 📞 Support

**Documentation:** https://docs.cineca-platform.com  
**Email:** support@cineca-platform.com  
**Status Page:** https://status.cineca-platform.com

---

**Version:** 1.0  
**Last Updated:** November 2, 2025  
**Next Update:** December 2, 2025
