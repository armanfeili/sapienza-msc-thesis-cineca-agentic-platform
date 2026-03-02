# Environment Variables Reference

Complete reference for all environment variables used by the Cineca Agentic Platform.

## Table of Contents

- [PostgreSQL Configuration](#postgresql-configuration)
- [Jobs System Configuration](#jobs-system-configuration)
- [Worker Configuration](#worker-configuration)
- [Redis Configuration](#redis-configuration)
- [Security & Authentication](#security--authentication)
- [Health Checks](#health-checks)
- [Observability](#observability)

---

## PostgreSQL Configuration

Database connection and pool configuration for PostgreSQL backend.

### `DB_HOST`
- **Type**: `string`
- **Default**: `postgres`
- **Description**: PostgreSQL server hostname or IP address
- **Example**: `localhost`, `postgres.example.com`, `10.0.0.5`
- **Docker**: Use service name from docker-compose (e.g., `postgres`)

### `DB_PORT`
- **Type**: `integer`
- **Default**: `5432`
- **Description**: PostgreSQL server port
- **Example**: `5432`, `15432`

### `DB_NAME`
- **Type**: `string`
- **Default**: `cineca_platform`
- **Description**: PostgreSQL database name
- **Example**: `cineca_platform`, `production_db`

### `DB_USER`
- **Type**: `string`
- **Default**: `cineca_user`
- **Description**: PostgreSQL database username
- **Example**: `cineca_user`, `app_user`
- **Security**: Use strong passwords, avoid default values in production

### `DB_PASSWORD`
- **Type**: `string`
- **Default**: `change_me_now`
- **Description**: PostgreSQL database password
- **Example**: `StrongP@ssw0rd123!`
- **Security**: **CRITICAL** - Must be changed in production, use secrets management

### `DB_SSLMODE`
- **Type**: `string`
- **Default**: `disable`
- **Options**: `disable`, `allow`, `prefer`, `require`, `verify-ca`, `verify-full`
- **Description**: PostgreSQL SSL/TLS connection mode
- **Example**: `require` (production), `disable` (development)
- **Security**: Use `require` or higher in production

### `DB_POOL_SIZE`
- **Type**: `integer`
- **Default**: `10`
- **Description**: Maximum number of connections in the database pool
- **Example**: `10` (development), `50` (production)
- **Tuning**: Adjust based on concurrent workload and database capacity

### `DB_POOL_TIMEOUT`
- **Type**: `integer` (seconds)
- **Default**: `30`
- **Description**: Timeout waiting for a connection from the pool
- **Example**: `30`, `60`
- **Tuning**: Increase if experiencing connection timeout errors

---

## Jobs System Configuration

Configuration for the PostgreSQL-backed jobs system.

### `USE_POSTGRES_JOBS`
- **Type**: `boolean`
- **Default**: `false`
- **Description**: Enable PostgreSQL-backed jobs system (required for worker)
- **Example**: `true`, `false`
- **Impact**: When `false`, uses in-memory jobs storage (not persistent)
- **Required**: Must be `true` for worker to function

### `ALLOWED_JOB_TYPES`
- **Type**: `string` (comma-separated)
- **Default**: `demo,test,long-running`
- **Description**: Comma-separated list of allowed job types
- **Example**: `demo,test,long-running`, `agent.run,data.process`
- **Usage**: Worker polls queues for each job type listed here
- **Validation**: Jobs with unlisted types are rejected at creation

### `JOB_STORE_BACKEND`
- **Type**: `string`
- **Default**: `memory`
- **Options**: `memory`, `postgres`
- **Description**: Backend storage for jobs (legacy setting)
- **Note**: Use `USE_POSTGRES_JOBS` instead for new deployments

---

## Worker Configuration

Configuration for the background worker service that processes jobs.

### `JOB_WORKER_POLL_INTERVAL`
- **Type**: `float` (seconds)
- **Default**: `1.0`
- **Description**: Interval between queue polling attempts
- **Example**: `1.0` (1 second), `0.5` (500ms), `5.0` (5 seconds)
- **Tuning**: 
  - Lower values = faster job pickup, higher Redis load
  - Higher values = slower job pickup, lower Redis load
- **Recommended**: `1.0` for most workloads

### `JOB_WORKER_HEARTBEAT_INTERVAL`
- **Type**: `float` (seconds)
- **Default**: `5.0`
- **Description**: Interval between job heartbeat updates
- **Example**: `5.0` (5 seconds), `10.0` (10 seconds)
- **Purpose**: Updates `job.updated_at` to indicate worker is alive
- **Monitoring**: Use this to detect stuck workers (no update = worker crashed)
- **Recommended**: `5.0` for most workloads

---

## Redis Configuration

### `REDIS_URL`
- **Type**: `string` (URL)
- **Default**: `redis://redis:6379/0`
- **Description**: Redis connection URL
- **Format**: `redis://[username:password@]host:port/db`
- **Example**: 
  - Development: `redis://localhost:6379/0`
  - Production: `redis://user:pass@redis.example.com:6379/0`
  - Docker: `redis://redis:6379/0`
- **Security**: Use password authentication in production

### `RATE_LIMIT_BACKEND`
- **Type**: `string`
- **Default**: `redis`
- **Options**: `redis`, `memory`
- **Description**: Backend for rate limiting
- **Example**: `redis` (recommended), `memory` (single instance only)

---

## Security & Authentication

### `OIDC_ISSUER`
- **Type**: `string` (URL)
- **Default**: None (required)
- **Description**: OIDC token issuer URL
- **Example**: `https://cineca.eu.auth0.com/`
- **Security**: Must match issuer in JWT tokens

### `OIDC_AUDIENCE`
- **Type**: `string`
- **Default**: None (required)
- **Description**: Expected audience claim in JWT tokens
- **Example**: `https://api.cineca-platform.eu`
- **Security**: Validates tokens are intended for this API

### `OIDC_JWKS_URL`
- **Type**: `string` (URL)
- **Default**: `{OIDC_ISSUER}/.well-known/jwks.json`
- **Description**: URL to fetch JSON Web Key Set for token verification
- **Example**: `https://cineca.eu.auth0.com/.well-known/jwks.json`
- **Security**: Public keys used to verify JWT signatures

### `ADMIN_TOKEN`
- **Type**: `string`
- **Default**: None (optional)
- **Description**: Shared secret for admin API endpoints
- **Example**: `admin-secret-token-12345`
- **Security**: **CRITICAL** - Use strong random value, rotate regularly
- **Usage**: Passed via `X-Admin-Token` header

### `ENABLE_ADMIN_ROUTES`
- **Type**: `boolean`
- **Default**: `1` (enabled)
- **Description**: Enable/disable admin API endpoints
- **Example**: `1`, `0`
- **Security**: Disable in production if not needed

### `SAFE_TOOLS`
- **Type**: `string` (comma-separated)
- **Default**: `system.health,system.status,system.metrics,graph.schema,graph.search`
- **Description**: Allow-list of tools accessible to basic users
- **Example**: `system.health,graph.search`
- **Security**: Limits tool access for unprivileged users

---

## Health Checks

### `ENFORCE_MIGRATIONS`
- **Type**: `boolean`
- **Default**: `0` (disabled)
- **Description**: Require migrations to be applied before reporting ready
- **Example**: `1`, `0`
- **Usage**: Set to `1` in production to enforce migration state
- **Behavior**: `/health/ready` returns 503 if migrations not applied

### `MIGRATIONS_APPLIED`
- **Type**: `boolean`
- **Default**: `false`
- **Description**: Flag indicating migrations have been applied
- **Example**: `true`, `false`
- **Internal**: Set by deployment scripts/entrypoint after migrations run

### `HEALTH_ALLOW_MG_HEALTH_FALLBACK`
- **Type**: `boolean`
- **Default**: `false`
- **Description**: Allow degraded health when Memgraph adapter is missing
- **Example**: `true`, `false`
- **Usage**: Set to `true` in environments without Memgraph

---

## Observability

### `LOG_LEVEL`
- **Type**: `string`
- **Default**: `INFO`
- **Options**: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`
- **Description**: Application logging level
- **Example**: `INFO` (production), `DEBUG` (development)

### `PROMETHEUS_METRICS_ENABLED`
- **Type**: `boolean`
- **Default**: `true`
- **Description**: Enable Prometheus metrics endpoint
- **Example**: `true`, `false`
- **Endpoint**: `/metrics`

### `ENABLE_DOCS`
- **Type**: `boolean`
- **Default**: `true`
- **Description**: Enable Swagger/OpenAPI documentation
- **Example**: `true`, `false`
- **Endpoints**: `/docs`, `/redoc`
- **Security**: Consider disabling in production

---

## Complete Example Configurations

### Development (Docker Compose)

```bash
# PostgreSQL
DB_HOST=postgres
DB_PORT=5432
DB_NAME=cineca_platform
DB_USER=cineca_user
DB_PASSWORD=dev_password
DB_SSLMODE=disable
DB_POOL_SIZE=10
DB_POOL_TIMEOUT=30

# Jobs System
USE_POSTGRES_JOBS=true
ALLOWED_JOB_TYPES=demo,test,long-running
JOB_WORKER_POLL_INTERVAL=1.0
JOB_WORKER_HEARTBEAT_INTERVAL=5.0

# Redis
REDIS_URL=redis://redis:6379/0

# Security
OIDC_ISSUER=https://cineca.eu.auth0.com/
OIDC_AUDIENCE=https://api.cineca-platform.eu
ENABLE_ADMIN_ROUTES=1
ADMIN_TOKEN=dev-admin-token

# Observability
LOG_LEVEL=DEBUG
PROMETHEUS_METRICS_ENABLED=true
ENABLE_DOCS=true
```

### Production

```bash
# PostgreSQL
DB_HOST=postgres-primary.internal.example.com
DB_PORT=5432
DB_NAME=cineca_platform
DB_USER=cineca_prod_user
DB_PASSWORD=${SECRET_DB_PASSWORD}  # From secrets management
DB_SSLMODE=verify-full
DB_POOL_SIZE=50
DB_POOL_TIMEOUT=60

# Jobs System
USE_POSTGRES_JOBS=true
ALLOWED_JOB_TYPES=agent.run,data.process,ml.train
JOB_WORKER_POLL_INTERVAL=1.0
JOB_WORKER_HEARTBEAT_INTERVAL=5.0

# Redis
REDIS_URL=redis://:${REDIS_PASSWORD}@redis.internal.example.com:6379/0

# Security
OIDC_ISSUER=https://auth.example.com/
OIDC_AUDIENCE=https://api.example.com
ENABLE_ADMIN_ROUTES=0  # Disabled in production
# ADMIN_TOKEN not set (use JWT-based admin auth instead)

# Health Checks
ENFORCE_MIGRATIONS=1

# Observability
LOG_LEVEL=INFO
PROMETHEUS_METRICS_ENABLED=true
ENABLE_DOCS=false  # Disabled in production
```

---

## Security Best Practices

1. **Never commit secrets** - Use environment-specific `.env` files (git-ignored)
2. **Rotate credentials** - Change `DB_PASSWORD`, `ADMIN_TOKEN` regularly
3. **Use secrets management** - Vault, AWS Secrets Manager, Kubernetes Secrets
4. **Enable TLS** - Set `DB_SSLMODE=require` in production
5. **Disable debug endpoints** - Set `ENABLE_DOCS=false`, `ENABLE_ADMIN_ROUTES=0`
6. **Validate tokens** - Ensure `OIDC_ISSUER` and `OIDC_AUDIENCE` are correct
7. **Restrict tool access** - Limit `SAFE_TOOLS` to minimum required set
8. **Monitor logs** - Set `LOG_LEVEL=INFO`, avoid DEBUG in production

---

## Troubleshooting

### Worker not processing jobs
- ✅ Check `USE_POSTGRES_JOBS=true`
- ✅ Verify `ALLOWED_JOB_TYPES` includes your job type
- ✅ Check worker logs: `docker compose logs worker -f`
- ✅ Test Redis: `curl http://localhost:8000/v1/health/redis`
- ✅ Test PostgreSQL: `curl http://localhost:8000/v1/health/db`

### Database connection errors
- ✅ Verify `DB_HOST`, `DB_PORT`, `DB_NAME` are correct
- ✅ Check `DB_USER` and `DB_PASSWORD` credentials
- ✅ Test connection: `psql -h $DB_HOST -U $DB_USER -d $DB_NAME`
- ✅ Check firewall/network connectivity
- ✅ Verify `DB_POOL_SIZE` not exceeding database limits

### Authentication failures
- ✅ Verify `OIDC_ISSUER` matches token issuer
- ✅ Check `OIDC_AUDIENCE` matches token audience claim
- ✅ Test JWKS URL: `curl $OIDC_JWKS_URL`
- ✅ Validate token claims match expected format

### Health check failures
- ✅ Check `/health/ready` for detailed status
- ✅ Review individual checks: `/health/db`, `/health/redis`
- ✅ Verify all dependencies are running
- ✅ Check logs for connection errors

---

**Last Updated**: 2025-10-12  
**Version**: 1.0  
**Related Docs**: [Configuration](./configuration.md), [Deployment](./deployment.md)
