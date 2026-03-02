# UI Deployment Guide

This guide walks you through deploying the Streamlit UI in development and production environments.

---

## Prerequisites

✅ **Backend API running** on `http://localhost:8000` (or configured URL)  
✅ **All backend services healthy**:
- PostgreSQL
- Redis
- Memgraph

✅ **Python 3.11+** installed  
✅ **Auth0 tenant configured** (for authentication)

---

## Quick Start (Development)

### 1. Verify Backend is Running

```bash
# Check backend health
curl http://localhost:8000/v1/health/live

# Expected: "ok"
```

### 2. Run Verification Script

```bash
# Verify all required endpoints exist
./scripts/verify_ui_backend.sh

# Expected: 15/15 endpoints operational
```

### 3. Configure Environment

Create `.env` file in project root (if not exists):

```bash
# Auth0 Configuration
AUTH0_DOMAIN=your-tenant.auth0.com
AUTH0_CLIENT_ID=your-client-id
AUTH0_AUDIENCE=https://your-api-audience

# API Configuration
API_BASE_URL=http://localhost:8000

# Optional: Streamlit Configuration
STREAMLIT_SERVER_PORT=8501
STREAMLIT_SERVER_ADDRESS=localhost
```

### 4. Install UI Dependencies

```bash
# Install Python dependencies
pip install -r requirements.txt

# Or use virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 5. Start Streamlit UI

```bash
# Start UI on http://localhost:8501
streamlit run ui/main.py

# Or with custom port
streamlit run ui/main.py --server.port 8502
```

### 6. Access UI

Open browser to: **http://localhost:8501**

**First-time Setup**:
1. Click "Login with Auth0"
2. Complete OAuth flow
3. Select tenant from dropdown
4. Navigate to features

---

## Production Deployment

### Option 1: Docker Deployment

#### Build UI Container

```bash
# Create Dockerfile for UI
cat > Dockerfile.ui <<EOF
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy UI code
COPY ui/ ./ui/

# Expose Streamlit port
EXPOSE 8501

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Run Streamlit
CMD ["streamlit", "run", "ui/main.py", "--server.port=8501", "--server.address=0.0.0.0"]
EOF

# Build container
docker build -f Dockerfile.ui -t cineca-ui:latest .

# Run container
docker run -d \
  --name cineca-ui \
  -p 8501:8501 \
  --env-file .env \
  cineca-ui:latest
```

#### Add to docker-compose.yml

```yaml
services:
  # ... existing services ...

  ui:
    build:
      context: .
      dockerfile: Dockerfile.ui
    ports:
      - "8501:8501"
    environment:
      - AUTH0_DOMAIN=${AUTH0_DOMAIN}
      - AUTH0_CLIENT_ID=${AUTH0_CLIENT_ID}
      - AUTH0_AUDIENCE=${AUTH0_AUDIENCE}
      - API_BASE_URL=http://backend:8000
    depends_on:
      - backend
    restart: unless-stopped
```

### Option 2: Cloud Deployment

#### Streamlit Cloud

1. **Push code to GitHub**:
   ```bash
   git add ui/
   git commit -m "Add Streamlit UI"
   git push origin main
   ```

2. **Deploy on Streamlit Cloud**:
   - Go to [share.streamlit.io](https://share.streamlit.io)
   - Connect GitHub repo
   - Select `ui/main.py` as main file
   - Add secrets (Auth0 credentials)
   - Deploy

3. **Configure Secrets**:
   In Streamlit Cloud dashboard, add secrets:
   ```toml
   [auth0]
   domain = "your-tenant.auth0.com"
   client_id = "your-client-id"
   audience = "https://your-api-audience"

   [api]
   base_url = "https://your-backend-api.com"
   ```

#### AWS (EC2 / ECS)

**EC2 Deployment**:
```bash
# SSH into EC2 instance
ssh ec2-user@your-instance-ip

# Clone repo
git clone https://github.com/your-org/cineca-agentic-platform.git
cd cineca-agentic-platform

# Install dependencies
pip install -r requirements.txt

# Configure environment
cat > .env <<EOF
AUTH0_DOMAIN=your-tenant.auth0.com
AUTH0_CLIENT_ID=your-client-id
AUTH0_AUDIENCE=https://your-api-audience
API_BASE_URL=http://backend:8000
EOF

# Run with systemd
sudo cat > /etc/systemd/system/cineca-ui.service <<EOF
[Unit]
Description=Cineca Streamlit UI
After=network.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/home/ec2-user/cineca-agentic-platform
EnvironmentFile=/home/ec2-user/cineca-agentic-platform/.env
ExecStart=/usr/local/bin/streamlit run ui/main.py --server.port=8501 --server.address=0.0.0.0
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# Start service
sudo systemctl daemon-reload
sudo systemctl enable cineca-ui
sudo systemctl start cineca-ui
```

**ECS Deployment**:
```bash
# Build and push to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 123456789.dkr.ecr.us-east-1.amazonaws.com
docker build -f Dockerfile.ui -t cineca-ui:latest .
docker tag cineca-ui:latest 123456789.dkr.ecr.us-east-1.amazonaws.com/cineca-ui:latest
docker push 123456789.dkr.ecr.us-east-1.amazonaws.com/cineca-ui:latest

# Create ECS task definition (task-definition.json)
{
  "family": "cineca-ui",
  "containerDefinitions": [
    {
      "name": "ui",
      "image": "123456789.dkr.ecr.us-east-1.amazonaws.com/cineca-ui:latest",
      "portMappings": [
        {
          "containerPort": 8501,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {"name": "AUTH0_DOMAIN", "value": "your-tenant.auth0.com"},
        {"name": "AUTH0_CLIENT_ID", "value": "your-client-id"},
        {"name": "AUTH0_AUDIENCE", "value": "https://your-api-audience"},
        {"name": "API_BASE_URL", "value": "http://backend:8000"}
      ],
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:8501/_stcore/health || exit 1"],
        "interval": 30,
        "timeout": 5,
        "retries": 3
      }
    }
  ],
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024"
}

# Register task definition
aws ecs register-task-definition --cli-input-json file://task-definition.json

# Create ECS service
aws ecs create-service \
  --cluster your-cluster \
  --service-name cineca-ui \
  --task-definition cineca-ui \
  --desired-count 2 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-123],securityGroups=[sg-123],assignPublicIp=ENABLED}"
```

---

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AUTH0_DOMAIN` | Yes | - | Auth0 tenant domain |
| `AUTH0_CLIENT_ID` | Yes | - | Auth0 application client ID |
| `AUTH0_AUDIENCE` | Yes | - | Auth0 API audience |
| `API_BASE_URL` | No | `http://localhost:8000` | Backend API base URL |
| `STREAMLIT_SERVER_PORT` | No | `8501` | UI port |
| `STREAMLIT_SERVER_ADDRESS` | No | `localhost` | UI bind address |
| `LOG_LEVEL` | No | `INFO` | Logging level |

### Streamlit Configuration (.streamlit/config.toml)

```toml
[server]
port = 8501
address = "0.0.0.0"
headless = true
enableCORS = false
enableXsrfProtection = true

[browser]
serverAddress = "your-domain.com"
serverPort = 443

[theme]
primaryColor = "#0066cc"
backgroundColor = "#ffffff"
secondaryBackgroundColor = "#f0f2f6"
textColor = "#262730"
font = "sans serif"

[client]
showErrorDetails = false
toolbarMode = "minimal"
```

---

## Health Checks

### UI Health Endpoint

Streamlit provides a built-in health endpoint:

```bash
curl http://localhost:8501/_stcore/health

# Expected: {"status": "ok"}
```

### Liveness Probe (Kubernetes)

```yaml
livenessProbe:
  httpGet:
    path: /_stcore/health
    port: 8501
  initialDelaySeconds: 30
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 3
```

### Readiness Probe (Kubernetes)

```yaml
readinessProbe:
  httpGet:
    path: /_stcore/health
    port: 8501
  initialDelaySeconds: 10
  periodSeconds: 5
  timeoutSeconds: 3
  successThreshold: 1
```

---

## Troubleshooting

### Issue: UI not loading (blank page)

**Diagnosis**:
```bash
# Check UI logs
docker logs cineca-ui

# Check if port is accessible
curl http://localhost:8501/_stcore/health
```

**Resolution**:
- Verify Streamlit is running: `ps aux | grep streamlit`
- Check firewall rules allow port 8501
- Verify `.env` file has correct values

### Issue: "Resource not found" errors

**Diagnosis**:
```bash
# Verify backend is running
./scripts/verify_ui_backend.sh

# Check backend health
curl http://localhost:8000/v1/health/live
```

**Resolution**:
- Ensure backend API is running on configured `API_BASE_URL`
- Verify `API_BASE_URL` in `.env` is correct
- Check network connectivity between UI and backend

### Issue: Authentication failures

**Diagnosis**:
```bash
# Check Auth0 configuration
echo $AUTH0_DOMAIN
echo $AUTH0_CLIENT_ID
echo $AUTH0_AUDIENCE
```

**Resolution**:
- Verify Auth0 credentials in `.env`
- Check Auth0 application is configured for SPA
- Add UI URL to Auth0 allowed callback URLs
- Verify Auth0 API audience matches backend

### Issue: 401 Unauthorized on all requests

**This is expected behavior** when:
- No Auth0 token is present
- Token has expired
- User hasn't logged in yet

**Resolution**:
1. Click "Login with Auth0" button
2. Complete OAuth flow
3. Token will be stored in session state
4. Requests will include `Authorization: Bearer <token>` header

### Issue: Data not loading (empty states)

**Diagnosis**:
```bash
# Check if backend has data
curl -H "Authorization: Bearer YOUR_TOKEN" http://localhost:8000/v1/models/defaults

# Check database is populated
docker exec -it cineca-postgres psql -U postgres -c "SELECT COUNT(*) FROM providers;"
```

**Resolution**:
- Run database initialization: `python db/populate.py`
- Verify backend services are healthy
- Check tenant is selected in UI dropdown

---

## Security Best Practices

### 1. Environment Variables

**❌ Never commit `.env` to Git**:
```bash
# Add to .gitignore
echo ".env" >> .gitignore
```

**✅ Use secrets management**:
- AWS Secrets Manager
- Azure Key Vault
- HashiCorp Vault
- Kubernetes Secrets

### 2. HTTPS/TLS

**Production deployments must use HTTPS**:

```nginx
# nginx reverse proxy
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 3. CORS Configuration

Backend must allow UI origin:

```python
# src/main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-ui-domain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 4. Rate Limiting

Protect against abuse:

```python
# Add to backend
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.get("/v1/models/defaults")
@limiter.limit("10/minute")
def get_defaults():
    ...
```

---

## Monitoring & Observability

### Metrics

**Streamlit Built-in Metrics**:
- Available at: `http://localhost:8501/_stcore/metrics`

**Custom Metrics** (using Prometheus):
```python
# ui/metrics.py
from prometheus_client import Counter, Histogram

# Track page views
page_views = Counter('ui_page_views_total', 'Total page views', ['page'])

# Track API call latency
api_latency = Histogram('ui_api_latency_seconds', 'API call latency', ['endpoint'])
```

### Logging

**Structured Logging**:
```python
# ui/main.py
import structlog

logger = structlog.get_logger()

logger.info("user_login", 
    user_id=st.session_state.user_id,
    tenant_id=st.session_state.tenant_id
)
```

**Log Aggregation**:
- CloudWatch Logs (AWS)
- Google Cloud Logging
- Azure Monitor
- ELK Stack
- Datadog

### Error Tracking

**Sentry Integration**:
```python
# ui/main.py
import sentry_sdk

sentry_sdk.init(
    dsn="https://your-sentry-dsn",
    environment="production",
    traces_sample_rate=0.1
)
```

---

## Performance Optimization

### 1. Caching

**Streamlit Caching**:
```python
# ui/api.py
import streamlit as st

@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_model_defaults():
    return api.get_model_defaults()
```

### 2. Connection Pooling

**HTTP Connection Pool**:
```python
# ui/api.py
import httpx

# Create persistent client
client = httpx.Client(
    base_url=API_BASE_URL,
    timeout=30.0,
    limits=httpx.Limits(max_keepalive_connections=10)
)
```

### 3. Lazy Loading

**Load data on-demand**:
```python
# ui/views/models.py
def _render_model_instances():
    if st.button("Load Instances"):
        instances = api.get_model_instances()
        st.session_state.instances = instances
```

---

## Deployment Checklist

### Pre-Deployment
- [ ] Backend API is running and healthy
- [ ] Database is initialized with default data
- [ ] Auth0 is configured and tested
- [ ] Environment variables are set correctly
- [ ] All dependencies are installed
- [ ] Backend verification script passes (15/15)

### Deployment
- [ ] UI container/service is deployed
- [ ] Health checks are passing
- [ ] HTTPS/TLS is configured (production only)
- [ ] CORS is configured correctly
- [ ] Firewall rules allow UI port

### Post-Deployment
- [ ] UI is accessible via browser
- [ ] Login flow works end-to-end
- [ ] All pages load without errors
- [ ] API calls succeed (no 404s)
- [ ] Data displays correctly
- [ ] Monitoring/logging is configured

---

## Support

### Documentation
- **Implementation Guide**: `docs/UI_IMPLEMENTATION_COMPLETE.md`
- **Verification Results**: `docs/UI_FIXES_APPLIED.md`
- **API Guide**: `docs/AGENTS_API_GUIDE.md`
- **Auth Guide**: `docs/AUTH_GUIDE.md`

### Testing
```bash
# Run backend verification
./scripts/verify_ui_backend.sh

# Run unit tests (if available)
pytest tests/ui/

# Run integration tests
pytest tests/integration/test_ui_backend.py
```

### Common Commands
```bash
# Start UI (development)
streamlit run ui/main.py

# Start UI (production)
streamlit run ui/main.py --server.port=8501 --server.address=0.0.0.0 --server.headless=true

# Check UI health
curl http://localhost:8501/_stcore/health

# Verify backend endpoints
./scripts/verify_ui_backend.sh

# View UI logs
docker logs -f cineca-ui
```

---

**Last Updated**: January 2025  
**Status**: Production Ready ✅
