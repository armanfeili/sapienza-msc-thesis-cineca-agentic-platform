# Cineca Agentic Platform - Streamlit UI

A comprehensive web interface for the Cineca Agentic Platform, providing full coverage of the API with role-aware access control and a polished user experience.

## 🎯 Features

### Authentication
- **Four identity types**: Admin, User, Machine (auto-managed)
- Auth0 integration with Password Realm and Client Credentials grants
- Token lifecycle management with auto-renewal
- Scope-based UI elements (features shown/hidden by permissions)

### Core Functionality
- **Dashboard**: Real-time health monitoring for all system components
- **Agents**: Copilot-style agent runs with live timeline of tool calls
- **Tools**: Schema-driven tool invocation with NL→Cypher support
- **Models**: Instance and provider management with health checks
- **Jobs**: User and admin job management with event streaming
- **Tenants**: Full CRUD operations for multi-tenancy
- **Admin**: Processes, manifests, ops, and database operations

### UX Highlights
- Live updates and polling for long-running operations
- Tabular data export (CSV/JSON)
- Raw JSON inspection with sanitized display
- Error tracking with trace IDs
- Detailed logging (tokens masked)
- Developer mode for internal endpoints

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Access to Cineca Agentic Platform API
- Auth0 credentials configured

### Local Development

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment:**
   Create a `.streamlit/secrets.toml` file or set environment variables:
   ```toml
   API_BASE_URL = "http://localhost:8000"
   
   AUTH0_DOMAIN = "cineca.eu.auth0.com"
   AUTH0_AUDIENCE = "api://cineca-agentic-platform"
   
   AUTH0_USER_CLIENT_ID = "your-user-client-id"
   AUTH0_USER_CLIENT_SECRET = "your-user-client-secret"
   AUTH0_MACHINE_CLIENT_ID = "your-machine-client-id"
   AUTH0_MACHINE_CLIENT_SECRET = "your-machine-client-secret"
   
   AUTH0_ADMIN_USERNAME = "admin@example.com"
   AUTH0_ADMIN_PASSWORD = "AdminPass123!"
   AUTH0_USER_USERNAME = "user@example.com"
   AUTH0_USER_PASSWORD = "UserPass123!"
   ```

3. **Run the application:**
   ```bash
   streamlit run app.py
   ```

4. **Access the UI:**
   Open [http://localhost:8501](http://localhost:8501) in your browser.

### Docker Deployment

1. **Build image:**
   ```bash
   docker build -t cineca-ui-streamlit .
   ```

2. **Run container:**
   ```bash
   docker run -p 8501:8501 \
     -e API_BASE_URL=http://api:8000 \
     -e AUTH0_DOMAIN=cineca.eu.auth0.com \
     -e AUTH0_AUDIENCE=api://cineca-agentic-platform \
     -e AUTH0_USER_CLIENT_ID=... \
     -e AUTH0_USER_CLIENT_SECRET=... \
     -e AUTH0_MACHINE_CLIENT_ID=... \
     -e AUTH0_MACHINE_CLIENT_SECRET=... \
     -e AUTH0_ADMIN_USERNAME=admin@example.com \
     -e AUTH0_ADMIN_PASSWORD=AdminPass123! \
     -e AUTH0_USER_USERNAME=user@example.com \
     -e AUTH0_USER_PASSWORD=UserPass123! \
     cineca-ui-streamlit
   ```

## 📋 Scope Requirements Matrix

| Tab/Feature | Required Scopes | Notes |
|-------------|----------------|-------|
| Auth | None | Always accessible |
| Dashboard | None | Health endpoints are public |
| Explore | None | OpenAPI spec is public |
| Agents (Runs) | `user:me` | Basic access |
| Agents (Sessions) | `user:me` | Basic access |
| Tools (List/View) | `user:me` | Basic access |
| Tools (Invoke Safe) | `tools:invoke:basic` | Safe tools only |
| Tools (Invoke All) | `tools:invoke:all` | All tools including admin |
| Models (List) | `user:me` | Read-only |
| Models (Create/Delete) | `admin:all` | Admin only |
| Providers | `admin:all` | Admin only |
| Tenants | `admin:all` | Admin only |
| Jobs (User) | `user:me` | Personal jobs |
| Jobs (Admin) | `admin:all` | All jobs collection |
| Admin (All) | `admin:all` | Admin only |
| Internal | `internal:all` + Dev Mode | Developer only |

## 🔒 Security Features

- **Token masking**: All tokens are masked in logs and UI displays
- **Scope enforcement**: UI elements disabled/hidden based on permissions
- **Request sanitization**: Sensitive fields redacted in JSON displays
- **Confirmation modals**: Dangerous actions require explicit confirmation
- **Audit logging**: All API calls logged with masked credentials

## 🏗️ Architecture

## 📁 Project Structure

```
ui_control_panel/
├── app.py                      # Main Streamlit application
├── state.py                    # Session state management
├── api.py                      # HTTP client & API wrappers

## 🔧 Configuration

### Environment Variables

- `API_BASE_URL`: Base URL for the API (default: `http://localhost:8000`)
- `AUTH0_DOMAIN`: Auth0 tenant domain
- `AUTH0_AUDIENCE`: Auth0 API audience
- `AUTH0_USER_CLIENT_ID`: User client ID
- `AUTH0_USER_CLIENT_SECRET`: User client secret
- `AUTH0_MACHINE_CLIENT_ID`: Machine client ID
- `AUTH0_MACHINE_CLIENT_SECRET`: Machine client secret
- `AUTH0_ADMIN_USERNAME`: Admin username
- `AUTH0_ADMIN_PASSWORD`: Admin password
- `AUTH0_USER_USERNAME`: Regular user username
- `AUTH0_USER_PASSWORD`: Regular user password

### Secrets Management

Use Streamlit secrets for sensitive values:

```toml
# .streamlit/secrets.toml
API_BASE_URL = "http://localhost:8000"
AUTH0_DOMAIN = "..."
# ... etc
```

## 📊 Usage Examples

### Running an Agent

1. Go to **Agents** tab
2. Enter a prompt in the text area
3. Optionally configure model and tenant
4. Click **Run Agent**
5. Watch the live timeline as the agent executes
6. View the final answer and export if needed

### Invoking NL→Cypher Tool

1. Go to **Tools** tab
2. Find the NL→Cypher tool (e.g., `graph.query`)
3. Click **View Schema** to see parameters
4. Enter your natural language query
5. Click **Invoke Tool**
6. View generated Cypher, parameters, and results table
7. Export results as CSV or JSON

### Managing Tenants (Admin)

1. Ensure you're logged in as Admin
2. Go to **Tenants** tab
3. Expand **Create New Tenant**
4. Fill in name and metadata
5. Click **Create Tenant**
6. Use the table to view/update/delete tenants

## 🐛 Troubleshooting

### Common Issues

#### Health Dashboard Shows Errors But Features Work

**Symptom:** Dashboard displays ❌ for Postgres, Redis, or Memgraph, but database operations succeed.

**Root Cause:** Health check timeout is set to 2.5 seconds, which is too strict for some operations. Services are functional but monitoring reports errors.

**Verification:**
```bash
# Check actual functionality
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/v1/admin/db/counts
# Should return: {"ok": true, "nodes": 1234, "edges": 5678}
```

**Solution:**
- **Option 1:** Accept monitoring warnings (services work fine)
- **Option 2:** Increase timeout in `src/settings.py`: `HEALTHCHECK_TIMEOUT_SECONDS = 5.0`
- **Option 3:** Restart services: `docker compose restart`

#### Agent Runs Return Demo Mode

**Symptom:** Agent run completes but shows `"(demo) You said: <prompt>"` instead of real execution.

**Root Cause:** Backend orchestrator implementation gap - `src/services/orchestrator.py` exists but `run()` method not implemented.

**Expected Behavior:** This is a known backend limitation, not a UI bug. The UI is fully functional and ready for when the orchestrator is implemented.

**Verification:**
```bash
# Check agent run response
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is 2+2?", "max_steps": 3}' \
  http://localhost:8000/v1/agent-runs | jq '.output'
# Returns: "(demo) You said: What is 2+2?"
```

**Current Status:** ❌ Backend work required, not operational issue

**Workaround:** Use other features that work fully:
- NL→Cypher generation and execution ✅
- Tool invocation ✅
- Session management ✅
- Admin workflows ✅

#### Memgraph Shows "Connection Error" But Cypher Works

**Symptom:** Health check reports Memgraph unavailable, but NL→Cypher and graph operations succeed.

**Root Cause:** Same health check timeout issue as above. The database is running and responsive.

**Verification:**
```bash
# Test Memgraph directly
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/v1/tools/graph.schema
# Should return graph schema
```

**Solution:** Same as "Health Dashboard Shows Errors" above.

#### Token Issues

**Symptom:** API returns 401 Unauthorized or token expired warnings.

**Diagnosis:**
- Check Auth0 credentials in environment/secrets
- Verify token hasn't expired (check badge countdown in UI header)
- Inspect token scopes: `curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/v1/auth/me | jq '.scopes'`

**Solutions:**
- **Expired token:** Click **Logout** → **Login** to refresh
- **Missing scopes:** Contact admin to grant required permissions
- **Invalid credentials:** Verify `.streamlit/secrets.toml` or environment variables
- **Manual token refresh:**
  ```bash
  # Fetch new tokens
  ./scripts/fetch_auth0_tokens.sh
  
  # Update environment
  export AUTH0_ADMIN_TOKEN='eyJhbGci...'
  ```

#### API Connection Errors

**Symptom:** UI shows "Failed to connect to API" or timeout errors.

**Diagnosis:**
- Verify `API_BASE_URL` is correct (check `.streamlit/secrets.toml`)
- Check API is running: `docker compose ps app` should show `Up (healthy)`
- Test connectivity: `curl http://localhost:8000/v1/health/live` should return `"ok"`

**Solutions:**
- **Wrong URL:** 
  - For Docker: `API_BASE_URL = "http://app:8000"`
  - For local dev: `API_BASE_URL = "http://localhost:8000"`
- **Service down:** `docker compose restart app`
- **Network issue:** `docker compose down && docker compose up -d`

#### Permission Errors

**Symptom:** UI shows "Insufficient permissions" or features are disabled.

**Diagnosis:**
- Check current scopes in **Auth** tab → "Token Info" section
- Compare with scope requirements in table above

**Solutions:**
- Verify your token has required scopes
- Log out and log back in to refresh scopes
- Contact admin for scope grants
- Use correct identity type (Admin vs User vs Machine)

## 📝 Logging

Logs are written to `logs/ui.log` with:
- Timestamp
- Log level
- Message
- Masked tokens (first 8 + last 8 chars only)

View logs in the **Log Pane** component (available in various tabs) or tail the file:

### View Logs

```bash
tail -f logs/ui.log
```

## 🤝 Contributing

When adding new features:

1. Add API wrapper to `api.py`
2. Create/update view in `views/`
3. Add components to `components/` if reusable
4. Update scope matrix in this README
5. Test with different permission levels

## 📄 License

See main project LICENSE file.

## 🔗 Related Documentation

- [API Documentation](../docs/)
- [Authentication Guide](../docs/AUTH_GUIDE.md)
- [Agents Implementation](../docs/AGENTS_README.md)
- [Security Audit](../SECURITY_AUDIT_REPORT.md)
