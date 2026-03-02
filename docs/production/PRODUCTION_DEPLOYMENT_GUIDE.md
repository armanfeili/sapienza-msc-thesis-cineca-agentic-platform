# Production Deployment Guide

**Version**: 1.0  
**Date**: November 1, 2025  
**Status**: Production-Ready

---

## Overview

This guide provides step-by-step instructions for deploying the Cineca Agentic Platform to production with full security hardening, HTTPS termination, rate limiting, and monitoring.

## Prerequisites

### Infrastructure Requirements

- **Operating System**: Ubuntu 22.04 LTS or similar (tested)
- **Docker**: 24.0+ with compose v2
- **Memory**: Minimum 8GB RAM (16GB recommended)
- **Storage**: Minimum 50GB available disk space
- **Network**: Public IP with ports 80, 443 accessible

### Required Credentials

- [ ] SSL/TLS certificate and private key (or Let's Encrypt setup)
- [ ] Database credentials (PostgreSQL)
- [ ] Redis password (recommended for production)
- [ ] JWT secret (at least 32 random characters)
- [ ] Auth0 credentials (if using OIDC)
- [ ] Ollama or external LLM provider access

## Quick Start (5-Minute Deployment)

```bash
# 1. Clone repository
git clone https://github.com/ILP-Thesis-2025/Cineca-Agentic-Platform.git
cd Cineca-Agentic-Platform

# 2. Configure environment
cp .env.example .env.production

# 3. Generate secrets
./scripts/generate_secrets.sh >> .env.production

# 4. Configure SSL certificates (see SSL Configuration section)
mkdir -p ops/nginx/ssl
# Copy your certificates to ops/nginx/ssl/platform.crt and platform.key

# 5. Start production stack
docker-compose -f docker-compose.yml -f docker-compose.nginx.yml up -d

# 6. Verify deployment
./scripts/test_production_hardening.sh

# 7. Configure defaults
# Visit https://your-domain.com → Admin → Providers → Set Default Provider
```

## Detailed Deployment Steps

### Step 1: Environment Configuration

Create `.env.production` with production-specific settings:

```bash
# App Configuration
APP_ENV=production
LOG_LEVEL=INFO
ENABLE_DOCS=false  # Disable Swagger UI in production

# Database (PostgreSQL)
DB_HOST=postgres
DB_PORT=5432
DB_NAME=cineca_production
DB_USER=cineca_prod
DB_PASSWORD=<GENERATE_STRONG_PASSWORD>
DB_SSLMODE=require  # Enable SSL for database connections

# Redis
REDIS_URL=redis://:your_redis_password@redis:6379/0

# Security
JWT_SECRET=<GENERATE_32_CHAR_SECRET>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

# OIDC (if using Auth0)
OIDC_ISSUER=https://your-tenant.auth0.com/
OIDC_AUDIENCE=https://platform.cineca.it/api
OIDC_JWKS_URL=https://your-tenant.auth0.com/.well-known/jwks.json

# Production Security
ENABLE_SECURITY_HEADERS=true
ENABLE_HSTS=true
HSTS_MAX_AGE=31536000  # 1 year
SECURE_COOKIES=true
TRUST_PROXY=true  # Trust X-Forwarded headers from nginx

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_BACKEND=redis
RATE_LIMIT_DEFAULT_LIMIT=60
RATE_LIMIT_DEFAULT_WINDOW=60

# CORS (adjust for your domain)
CORS_ALLOWED_ORIGINS=https://platform.cineca.it
CORS_ALLOWED_METHODS=GET,POST,PUT,DELETE,OPTIONS

# Observability
PROMETHEUS_METRICS_ENABLED=true
OTEL_SERVICE_NAME=cineca-agentic-platform
```

### Step 2: Generate Secrets

Use provided script to generate strong secrets:

```bash
#!/bin/bash
# scripts/generate_secrets.sh

echo "# Generated Secrets - $(date)"
echo "JWT_SECRET=$(openssl rand -base64 32)"
echo "DB_PASSWORD=$(openssl rand -base64 32 | tr -d '=+/' | cut -c1-32)"
echo "REDIS_PASSWORD=$(openssl rand -base64 32 | tr -d '=+/' | cut -c1-32)"
```

### Step 3: SSL/TLS Certificate Setup

#### Option A: Let's Encrypt (Recommended for Production)

```bash
# Install certbot
sudo apt-get update
sudo apt-get install certbot

# Obtain certificate
sudo certbot certonly --standalone \
  --non-interactive \
  --agree-tos \
  --email admin@cineca.it \
  -d platform.cineca.it

# Copy to nginx directory
sudo cp /etc/letsencrypt/live/platform.cineca.it/fullchain.pem ops/nginx/ssl/platform.crt
sudo cp /etc/letsencrypt/live/platform.cineca.it/privkey.pem ops/nginx/ssl/platform.key

# Set permissions
sudo chmod 644 ops/nginx/ssl/platform.crt
sudo chmod 600 ops/nginx/ssl/platform.key

# Setup auto-renewal
sudo certbot renew --dry-run
```

#### Option B: Custom Certificate

```bash
# Copy your certificates
cp /path/to/your/certificate.crt ops/nginx/ssl/platform.crt
cp /path/to/your/private.key ops/nginx/ssl/platform.key

# Set proper permissions
chmod 644 ops/nginx/ssl/platform.crt
chmod 600 ops/nginx/ssl/platform.key
```

#### Option C: Self-Signed (Development/Testing Only)

```bash
# Generate self-signed certificate
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout ops/nginx/ssl/platform.key \
  -out ops/nginx/ssl/platform.crt \
  -subj "/CN=localhost/O=Cineca Platform/C=IT"
```

### Step 4: Database Initialization

```bash
# Start PostgreSQL first
docker-compose up -d postgres

# Wait for healthy status
docker-compose ps postgres

# Run migrations
docker-compose run --rm app python -m alembic upgrade head

# Seed initial data (optional)
docker-compose run --rm app python db/postgres_control/seed_tenants.py
```

### Step 5: Start Production Stack

```bash
# Start all services with nginx
docker-compose -f docker-compose.yml -f docker-compose.nginx.yml up -d

# View logs
docker-compose logs -f

# Check health
curl https://platform.cineca.it/v1/health/ready
```

### Step 6: Post-Deployment Verification

Run the production hardening test suite:

```bash
# Test HTTPS, security headers, rate limiting
./scripts/test_production_hardening.sh

# Expected output:
# ✓ PASS: HTTP redirect
# ✓ PASS: HTTPS connectivity
# ✓ PASS: HSTS header
# ✓ PASS: X-Frame-Options
# ✓ PASS: X-Content-Type-Options
# ✓ PASS: X-XSS-Protection
# ✓ PASS: Referrer-Policy
# ✓ PASS: Server header removal
# ✓ PASS: Rate limiting
```

### Step 7: Configure Default Provider

**⚠️ IMPORTANT**: The application performs a startup provider health check. If no default provider is configured or the default provider is unreachable, the application will:
- **Production mode**: Fail fast with a clear error message
- **Dev/Demo mode**: Continue with warnings (for development convenience)

1. **Via UI** (Recommended):
   ```
   Navigate to: https://platform.cineca.it
   1. Click "Admin" tab
   2. Go to "Providers" section
   3. Click "Set as Default" on your Ollama provider
   ```

2. **Via API**:
   ```bash
   # Get admin token
   TOKEN=$(curl -X POST https://platform.cineca.it/v1/auth/token \
     -H "Content-Type: application/json" \
     -d '{"username":"admin","password":"admin"}' | jq -r '.access_token')
   
   # Set default provider
   curl -X POST https://platform.cineca.it/v1/admin/models/providers/1:setDefault \
     -H "Authorization: Bearer $TOKEN"
   ```

### Provider Requirements

#### Required Providers at Startup

The platform requires at least one LLM provider to be configured before startup completes:

1. **Default Provider**: A global default provider should be set via the admin interface
2. **Provider Health**: The default provider must be reachable (health check passes)
3. **Provider Types**: Supported types include:
   - `openai_compatible` - OpenAI-compatible APIs (Ollama, Azure OpenAI, etc.)
   - `custom` - Custom provider implementations

#### Startup Behavior

**Production Mode** (`APP_ENV=production`):
- Application fails fast if no provider is configured
- Application fails fast if default provider is unreachable
- Clear error messages logged: `"provider.startup.unhealthy"`
- Startup blocked until provider is available

**Development/Demo Mode** (`APP_ENV=dev` or `DEMO_MODE=true`):
- Application continues with warnings if no provider exists
- Application continues with warnings if provider is unreachable
- Logs: `"provider.startup.degraded_but_continuing"`

#### Startup Provider Check

The application automatically performs a provider health check on startup:

```python
# Startup sequence:
1. Check for default provider (global scope)
2. If no default, check for any registered provider
3. Perform health check (HTTP GET to provider base_url/models)
4. Log result or fail fast based on environment
```

**Health Check Details**:
- **Endpoint**: `{base_url}/models` (OpenAI-compatible)
- **Timeout**: 5 seconds
- **Expected Response**: HTTP 200 OK
- **Failure Modes**: Timeout, connection refused, HTTP error

#### Model Warm-up

After provider health check, the application attempts to warm up the default model:

- **Non-fatal**: Warm-up failures do not block startup
- **Timeout**: 10 seconds maximum
- **Test Prompt**: Simple "Test" completion with 5 tokens
- **Purpose**: Pre-loads model to reduce first-request latency

#### Recovery Procedures

**If Provider Unavailable at Startup**:

1. **Check Provider Status**:
   ```bash
   # View provider logs
   docker compose logs app | grep -i "provider.startup"
   
   # Check provider health manually
   curl http://localhost:8000/v1/admin/models/providers/{provider_id}/health
   ```

2. **Restart Provider Service** (if using Ollama):
   ```bash
   docker compose restart ollama
   # Wait for Ollama to be ready
   docker compose logs ollama | grep -i "ready"
   ```

3. **Restart Application**:
   ```bash
   docker compose restart app
   # Verify startup logs
   docker compose logs app | grep -i "provider.startup.ready"
   ```

4. **Verify Provider Configuration**:
   ```bash
   # Check if provider exists
   curl http://localhost:8000/v1/admin/models/providers \
     -H "Authorization: Bearer $TOKEN"
   
   # Check if default is set
   curl http://localhost:8000/v1/admin/models/providers/defaults \
     -H "Authorization: Bearer $TOKEN"
   ```

**If No Providers Configured**:

1. **Register Provider** (via UI or API):
   ```bash
   # Example: Register Ollama provider
   curl -X POST http://localhost:8000/v1/admin/models/providers \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "ollama-local",
       "type": "openai_compatible",
       "base_url": "http://ollama:11434",
       "tenant_id": "global"
     }'
   ```

2. **Set as Default**:
   ```bash
   curl -X POST http://localhost:8000/v1/admin/models/providers/{provider_id}/setDefault \
     -H "Authorization: Bearer $TOKEN"
   ```

3. **Restart Application**:
   ```bash
   docker compose restart app
   ```

## Security Hardening Checklist

### Network Security

- [x] HTTPS enabled with valid certificate
- [x] HTTP to HTTPS redirect configured
- [x] HSTS header enabled (1 year max-age)
- [x] Firewall rules configured (allow 80, 443; deny direct access to 8000, 8501)
- [ ] VPN or bastion host for admin access (optional)
- [ ] IP allowlist for admin endpoints (optional)

### Application Security

- [x] Security headers middleware enabled
- [x] X-Frame-Options: DENY
- [x] X-Content-Type-Options: nosniff
- [x] X-XSS-Protection: 1; mode=block
- [x] Referrer-Policy configured
- [x] Content-Security-Policy (optional, configure as needed)
- [x] Server header removed
- [x] CORS restricted to specific origins
- [x] Rate limiting enabled (Redis-backed)
- [x] Secure cookies enabled

### Authentication & Authorization

- [ ] JWT secret changed from default (32+ characters)
- [ ] OIDC configured (Auth0 or similar)
- [ ] Admin users created with strong passwords
- [ ] Default admin password changed
- [ ] Token expiration configured appropriately
- [ ] Scope-based access control verified

### Database Security

- [ ] Database password changed from default
- [ ] Database SSL/TLS enabled
- [ ] Database access restricted to application only
- [ ] Database backups configured
- [ ] Connection pooling optimized

### Secrets Management

- [ ] All secrets moved to environment variables
- [ ] .env.production not committed to git
- [ ] Secrets rotated regularly (quarterly)
- [ ] Secret rotation procedure documented

## Monitoring & Observability

### Prometheus Metrics

Access metrics at: http://internal-network/metrics (restricted to internal IPs)

Key metrics to monitor:
- `http_requests_total` - Total HTTP requests
- `http_request_duration_seconds` - Request latency
- `rate_limit_exceeded_total` - Rate limit violations
- `db_connections_active` - Database connection pool usage
- `redis_commands_total` - Redis operation count

### Grafana Dashboards

1. **Health Overview**: System component status
2. **API Performance**: Request rates, latency, errors
3. **Security**: Rate limiting, auth failures, suspicious activity
4. **Resources**: CPU, memory, disk usage

Access Grafana: http://internal-network:3000 (admin/admin)

### Log Aggregation

Configure log forwarding to centralized logging:

```yaml
# docker-compose.yml
services:
  app:
    logging:
      driver: "syslog"
      options:
        syslog-address: "tcp://logstash.internal:5000"
        tag: "cineca-platform-app"
```

## Backup & Disaster Recovery

### Automated Backups

Configure daily backups:

```bash
# Add to crontab
0 2 * * * /app/ops/backup/backup.sh

# Backup script creates:
# - PostgreSQL dump
# - Redis RDB snapshot
# - Memgraph dump
# - Environment configuration
```

### Backup Verification

Weekly backup restoration drill:

```bash
# Test restore procedure
./ops/backup/dr-drill.sh

# Expected: Full restore completes in < 15 minutes
```

### Disaster Recovery Plan

1. **RTO (Recovery Time Objective)**: 1 hour
2. **RPO (Recovery Point Objective)**: 24 hours (daily backups)

**Recovery Steps**:
```bash
# 1. Provision new infrastructure
# 2. Restore from backup
./ops/backup/restore.sh s3://backups/latest

# 3. Verify health
curl https://platform.cineca.it/v1/health/ready

# 4. Validate functionality
./scripts/smoke_test.sh
```

## Scaling & Performance

### Horizontal Scaling

Scale application instances:

```bash
# Scale app service
docker-compose up -d --scale app=3

# Update nginx upstream
# Edit ops/nginx/nginx.conf:
upstream app_backend {
    server app1:8000;
    server app2:8000;
    server app3:8000;
}
```

### Vertical Scaling

Increase resource limits:

```yaml
# docker-compose.yml
services:
  app:
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
        reservations:
          cpus: '2'
          memory: 4G
```

### Performance Tuning

- **Database Connection Pool**: Increase pool size for high traffic
  ```
  DB_POOL_SIZE=20
  DB_POOL_MAX_OVERFLOW=40
  ```

- **Redis Connection Pool**: Optimize for concurrent requests
  ```
  REDIS_MAX_CONNECTIONS=50
  ```

- **Rate Limits**: Adjust based on traffic patterns
  ```
  RATE_LIMIT_DEFAULT_LIMIT=100  # requests per window
  RATE_LIMIT_DEFAULT_WINDOW=60  # seconds
  ```

## Maintenance Procedures

### Rolling Updates

Zero-downtime deployment:

```bash
# 1. Pull latest changes
git pull origin main

# 2. Build new image
docker-compose build app

# 3. Rolling update (one instance at a time)
docker-compose up -d --no-deps --scale app=2 app
sleep 30  # Wait for new instance to be healthy
docker-compose up -d --no-deps --scale app=1 app
```

### Database Migrations

Run migrations safely:

```bash
# 1. Backup database first
./ops/backup/backup.sh

# 2. Test migration on staging
docker-compose run --rm app python -m alembic upgrade head --sql > migration.sql

# 3. Apply migration
docker-compose run --rm app python -m alembic upgrade head

# 4. Verify
docker-compose logs app | grep migration
```

### Certificate Renewal

Auto-renewal with Let's Encrypt:

```bash
# Test renewal
sudo certbot renew --dry-run

# Force renewal (if needed)
sudo certbot renew --force-renewal

# Reload nginx
docker-compose restart nginx
```

## Troubleshooting

### Common Issues

**Issue**: 502 Bad Gateway
```bash
# Check backend health
docker-compose ps app
docker-compose logs app

# Restart app if needed
docker-compose restart app
```

**Issue**: Rate limit too aggressive
```bash
# Temporarily increase limits
# Edit .env.production:
RATE_LIMIT_DEFAULT_LIMIT=200

# Restart
docker-compose restart app
```

**Issue**: High memory usage
```bash
# Check memory stats
docker stats

# Increase memory limit or scale horizontally
docker-compose up -d --scale app=2
```

**Issue**: Certificate expired
```bash
# Renew certificate
sudo certbot renew --force-renewal

# Copy new certificate
sudo cp /etc/letsencrypt/live/platform.cineca.it/fullchain.pem ops/nginx/ssl/platform.crt
sudo cp /etc/letsencrypt/live/platform.cineca.it/privkey.pem ops/nginx/ssl/platform.key

# Reload nginx
docker-compose restart nginx
```

## Support & Contact

For production issues:
- **Email**: support@cineca.it
- **Emergency Hotline**: +39 XXX XXX XXXX
- **Documentation**: https://docs.cineca.it
- **Status Page**: https://status.cineca.it

---

**Last Updated**: November 1, 2025  
**Version**: 1.0  
**Maintained by**: Platform Engineering Team

