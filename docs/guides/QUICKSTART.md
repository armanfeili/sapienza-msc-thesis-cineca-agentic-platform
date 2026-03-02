# 🚀 Quick Start Guide

Get the Streamlit UI running in under 5 minutes!

## Prerequisites

- Python 3.11+
- Cineca Agentic Platform API running (default: `http://localhost:8000`)
- Auth0 credentials (see `.env` in project root)

## Option 1: Local Development (Recommended for Development)

### Step 1: Install Dependencies

```bash
./setup.sh
```

This will:
- Create a virtual environment
- Install all dependencies
- Create a secrets template

### Step 2: Configure Secrets

Edit `.streamlit/secrets.toml`:

```toml
API_BASE_URL = "http://localhost:8000"

AUTH0_DOMAIN = "cineca.eu.auth0.com"
AUTH0_AUDIENCE = "api://cineca-agentic-platform"

# Copy these from your project's .env file
AUTH0_USER_CLIENT_ID = "..."
AUTH0_USER_CLIENT_SECRET = "..."
AUTH0_MACHINE_CLIENT_ID = "..."
AUTH0_MACHINE_CLIENT_SECRET = "..."

AUTH0_ADMIN_USERNAME = "admin@example.com"
AUTH0_ADMIN_PASSWORD = "AdminPass123!"
AUTH0_USER_USERNAME = "user@example.com"
AUTH0_USER_PASSWORD = "UserPass123!"
```

### Step 3: Run

```bash
source .venv/bin/activate
streamlit run app.py
```

**Open**: http://localhost:8501

## Option 2: Docker (Recommended for Production)

### Step 1: Build

```bash
docker build -t cineca-ui-streamlit .
```

### Step 2: Run

```bash
docker run -p 8501:8501 \
  -e API_BASE_URL=http://localhost:8000 \
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

**Open**: http://localhost:8501

## Option 3: Docker Compose

### Step 1: Update Environment

Ensure your project's `.env` file has all Auth0 credentials.

### Step 2: Run

```bash
docker-compose up --build
```

**Open**: http://localhost:8501

## First-Time Usage

1. **Go to Auth Tab**
   - Click "Login Admin" or "Login User"
   - Machine token auto-fetches on startup

2. **Check Dashboard**
   - Verify all components are healthy
   - Enable auto-refresh if desired

3. **Try an Agent Run**
   - Go to Agents tab
   - Enter a prompt like "What can you help me with?"
   - Watch the Copilot-style timeline

4. **Explore Tools**
   - Go to Tools tab
   - View available tools
   - Try invoking a safe tool

5. **Test NL→Cypher**
   - Find the graph query tool
   - Enter a natural language query
   - See generated Cypher and results

## Troubleshooting

### "Connection refused"
- Ensure API is running: `curl http://localhost:8000/health/live`
- Check `API_BASE_URL` in secrets

### "Auth failed"
- Verify Auth0 credentials in `.env` or secrets
- Check tokens in project root: `cat .env | grep TOKEN`

### "Permission denied"
- Check your token has required scopes
- Admin features require `admin:all` scope
- Log out and log back in to refresh

### "Module not found"
- Activate virtual environment: `source .venv/bin/activate`
- Reinstall: `pip install -r requirements.txt`

## Key Features to Try

✅ **Four Auth Buttons** - Login/logout for Admin, User, and auto Machine token

✅ **Health Dashboard** - Real-time monitoring of all components

✅ **Agent Runs** - Copilot-style execution with live timeline

✅ **NL→Cypher** - Natural language to Memgraph queries

✅ **Jobs** - Create, monitor, and stream events

✅ **Tools** - Discover and invoke all available tools

✅ **Models** - Manage instances and providers

✅ **Tenants** - Full CRUD (admin only)

✅ **Admin Ops** - Processes, manifests, database operations

## Need Help?

- **README**: `./README.md` - Full documentation
- **Implementation Summary**: `./IMPLEMENTATION_SUMMARY.md` - Feature checklist
- **API Docs**: http://localhost:8000/docs (when API is running)
- **Logs**: `tail -f logs/ui.log`

## Development Tips

- Enable **Developer Mode** toggle in header to access internal endpoints
- Use **Log Pane** in various tabs to debug issues
- Check **Error Panel** for recent errors with trace IDs
- Export data as **CSV/JSON** from any table
- Use **JSON Drawer** to inspect raw API responses

## Next Steps

1. Try all tabs and features
2. Test different permission levels (Admin vs User)
3. Explore the NL→Cypher functionality
4. Run an agent with tool calls
5. Check out the Admin operations

Enjoy using the Cineca Agentic Platform! 🎉
