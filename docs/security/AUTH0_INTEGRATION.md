# Auth0 Integration Guide

## Overview

This document describes the Auth0 integration for the Cineca Agentic Platform, including how to fetch and use authentication tokens for testing and development.

## Auth0 Configuration

### Tenant Information
- **Domain**: `cineca.eu.auth0.com`
- **Audience**: `api://cineca-agentic-platform`
- **JWKS URL**: `https://cineca.eu.auth0.com/.well-known/jwks.json`

### Clients

#### 1. User Client (Password Realm Grant)
- **Client ID**: `kwkf1bGn2NmdKWzioZYkvtYM022dzb5C`
- **Grant Type**: `password` (Resource Owner Password Credentials)
- **Use Case**: User authentication for testing admin and regular user flows
- **Scopes**:
  - Admin: `user:me tools:invoke:all admin:all`
  - Regular User: `user:me tools:invoke:basic`

#### 2. Machine Client (Client Credentials Grant)
- **Client ID**: `OrcZzF86Wvh4DaSaaRf7uHLFRNpqa40N`
- **Grant Type**: `client_credentials`
- **Use Case**: Service-to-service authentication, background jobs
- **Scopes**: `internal:all`

### Test Users

#### Admin User
- **Email**: `admin@example.com`
- **Password**: `AdminPass123!`
- **Scopes**: `user:me tools:invoke:all admin:all`
- **Use Case**: Testing administrative endpoints and privileged operations

#### Regular User
- **Email**: `user@example.com`
- **Password**: `UserPass123!`
- **Scopes**: `user:me tools:invoke:basic`
- **Use Case**: Testing standard user endpoints with limited permissions

## Token Fetching

### Using the Token Fetching Script

The platform includes a comprehensive token fetching script at `scripts/fetch_auth0_tokens.sh`.

#### Prerequisites

1. **Install jq** (JSON processor):
   ```bash
   # macOS
   brew install jq
   
   # Ubuntu/Debian
   sudo apt-get install jq
   
   # RHEL/CentOS
   sudo yum install jq
   ```

2. **Configure .env file**: Ensure your `.env` file contains the Auth0 credentials (already configured if you're reading this).

#### Usage

**1. Display tokens in console (default)**:
```bash
./scripts/fetch_auth0_tokens.sh
```

This will:
- Fetch all three token types (admin, user, machine)
- Display token information including expiry times
- Show usage examples

**2. Save tokens to .env file**:
```bash
./scripts/fetch_auth0_tokens.sh --save-to-env
```

This will:
- Fetch all three tokens
- Create a backup of your `.env` file (`.env.backup.TIMESTAMP`)
- Append tokens to `.env` as:
  - `AUTH0_ADMIN_TOKEN`
  - `AUTH0_USER_TOKEN`
  - `AUTH0_MACHINE_TOKEN`

**3. Export to current shell**:
```bash
./scripts/fetch_auth0_tokens.sh --export
```

This will export the tokens to your current shell session.

### Token Information

Each token is valid for **24 hours** (86400 seconds). The script displays:
- Token type (Admin/User/Machine)
- Expiration time in seconds and hours
- Exact expiry date/time
- Permissions (for user tokens)

### Manual Token Fetching

If you need to fetch tokens manually via curl:

#### Admin Token (Password Realm)
```bash
curl --request POST \
  --url https://cineca.eu.auth0.com/oauth/token \
  --header "content-type: application/json" \
  --data '{
    "grant_type": "password",
    "username": "admin@example.com",
    "password": "AdminPass123!",
    "audience": "api://cineca-agentic-platform",
    "scope": "user:me tools:invoke:all admin:all",
    "client_id": "kwkf1bGn2NmdKWzioZYkvtYM022dzb5C",
    "client_secret": "z8Qf1DeYl-6fDKlGn5tpOuAshkjhiJmNrYkPibfBoR5vA5VC_7qznoavBN0rSZEB"
  }'
```

#### User Token (Password Realm)
```bash
curl --request POST \
  --url https://cineca.eu.auth0.com/oauth/token \
  --header "content-type: application/json" \
  --data '{
    "grant_type": "password",
    "username": "user@example.com",
    "password": "UserPass123!",
    "audience": "api://cineca-agentic-platform",
    "scope": "user:me tools:invoke:basic",
    "client_id": "kwkf1bGn2NmdKWzioZYkvtYM022dzb5C",
    "client_secret": "z8Qf1DeYl-6fDKlGn5tpOuAshkjhiJmNrYkPibfBoR5vA5VC_7qznoavBN0rSZEB"
  }'
```

#### Machine Token (Client Credentials)
```bash
curl --request POST \
  --url https://cineca.eu.auth0.com/oauth/token \
  --header "content-type: application/json" \
  --data '{
    "grant_type": "client_credentials",
    "client_id": "OrcZzF86Wvh4DaSaaRf7uHLFRNpqa40N",
    "client_secret": "i7rLVZpe4ehgP4wUBuo3cSd-w3kP3a0hghEJshpv52Fw1tJfs3uGa6JOg-te9NSE",
    "audience": "api://cineca-agentic-platform"
  }'
```

## Using Tokens

### Environment Variables

After running `./scripts/fetch_auth0_tokens.sh --save-to-env`, tokens are available as:

```bash
# Load from .env if needed
source .env

# Use in curl commands
curl -H "Authorization: Bearer $AUTH0_ADMIN_TOKEN" \
  http://localhost:8000/v1/user/me
```

### Testing Endpoints

#### Admin Endpoints
```bash
# Get current user info
curl -H "Authorization: Bearer $AUTH0_ADMIN_TOKEN" \
  http://localhost:8000/v1/user/me

# Admin-only operations
curl -H "Authorization: Bearer $AUTH0_ADMIN_TOKEN" \
  http://localhost:8000/v1/admin/processes

# Invoke any tool
curl -X POST \
  -H "Authorization: Bearer $AUTH0_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"tool_id": "system.health", "arguments": {}}' \
  http://localhost:8000/v1/tools/invoke
```

#### User Endpoints
```bash
# Get current user info
curl -H "Authorization: Bearer $AUTH0_USER_TOKEN" \
  http://localhost:8000/v1/user/me

# Invoke safe tools only
curl -X POST \
  -H "Authorization: Bearer $AUTH0_USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"tool_id": "system.health", "arguments": {}}' \
  http://localhost:8000/v1/tools/invoke
```

#### Machine Endpoints
```bash
# Health check
curl -H "Authorization: Bearer $AUTH0_MACHINE_TOKEN" \
  http://localhost:8000/v1/health

# Service-to-service calls
curl -X POST \
  -H "Authorization: Bearer $AUTH0_MACHINE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"data": "value"}' \
  http://localhost:8000/v1/internal/endpoint
```

### Python Requests

```python
import os
import requests

# Load token from environment
admin_token = os.getenv("AUTH0_ADMIN_TOKEN")

# Make authenticated request
headers = {"Authorization": f"Bearer {admin_token}"}
response = requests.get("http://localhost:8000/v1/user/me", headers=headers)
print(response.json())
```

### pytest Tests

```python
import os
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def admin_token():
    """Fixture providing real Auth0 admin token"""
    return os.getenv("AUTH0_ADMIN_TOKEN")

def test_admin_endpoint(client: TestClient, admin_token: str):
    """Test admin endpoint with real Auth0 token"""
    response = client.get(
        "/v1/user/me",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
```

## Token Validation

The platform validates tokens using:

1. **JWKS Verification**: Fetches public keys from Auth0's JWKS endpoint
2. **Signature Verification**: Validates JWT signature using RS256 algorithm
3. **Claims Validation**:
   - `iss`: Must match `https://cineca.eu.auth0.com/`
   - `aud`: Must match `api://cineca-agentic-platform`
   - `exp`: Token must not be expired
   - `scope`: Used for permission-based authorization

## Permissions & Scopes

### Admin Scopes
- `user:me`: Access user profile information
- `tools:invoke:all`: Invoke any tool including privileged ones
- `admin:all`: Access administrative endpoints

### User Scopes
- `user:me`: Access user profile information
- `tools:invoke:basic`: Invoke safe tools only (defined in `SAFE_TOOLS` env var)

### Machine Scopes
- `internal:all`: Service-to-service operations

## Security Best Practices

### Development
- ✅ Tokens are automatically saved with restricted permissions (600)
- ✅ `.env` backups are created before updating
- ✅ Tokens expire after 24 hours
- ✅ Never commit tokens to version control (`.env` is gitignored)

### Production
- 🔒 Use environment variables or secrets management (AWS Secrets Manager, Azure Key Vault, etc.)
- 🔒 Rotate client secrets regularly
- 🔒 Use shorter token expiration times
- 🔒 Implement token refresh flows
- 🔒 Monitor token usage and anomalies
- 🔒 Disable password realm grant in production (use OAuth2 authorization code flow instead)

## Troubleshooting

### "jq: command not found"
Install jq using your package manager (see Prerequisites above).

### "ERROR: Missing required environment variables"
Ensure your `.env` file contains all Auth0 configuration:
```bash
AUTH0_DOMAIN=cineca.eu.auth0.com
AUTH0_AUDIENCE=api://cineca-agentic-platform
AUTH0_USER_CLIENT_ID=...
AUTH0_USER_CLIENT_SECRET=...
AUTH0_MACHINE_CLIENT_ID=...
AUTH0_MACHINE_CLIENT_SECRET=...
AUTH0_ADMIN_USERNAME=...
AUTH0_ADMIN_PASSWORD=...
AUTH0_USER_USERNAME=...
AUTH0_USER_PASSWORD=...
```

### "Failed to fetch token: Unauthorized"
- Check client ID and secret are correct
- Verify username and password for password realm grant
- Ensure Auth0 tenant and audience are correct

### "Token validation failed"
- Token may be expired (valid for 24 hours)
- Re-fetch tokens using `./scripts/fetch_auth0_tokens.sh --save-to-env`
- Verify `OIDC_ISSUER` and `OIDC_AUDIENCE` in `.env` match Auth0 configuration

## Integration with CI/CD

For automated testing in CI/CD pipelines:

```yaml
# GitHub Actions example
- name: Fetch Auth0 tokens
  env:
    AUTH0_DOMAIN: ${{ secrets.AUTH0_DOMAIN }}
    AUTH0_USER_CLIENT_ID: ${{ secrets.AUTH0_USER_CLIENT_ID }}
    AUTH0_USER_CLIENT_SECRET: ${{ secrets.AUTH0_USER_CLIENT_SECRET }}
    # ... other secrets
  run: |
    ./scripts/fetch_auth0_tokens.sh --save-to-env
    source .env
    
- name: Run integration tests
  run: |
    pytest tests/integration/ -v
```

## Related Documentation

- [Authentication Implementation](./P2_5_SECRETS_HARDENING_COMPLETE.md)
- [Security Audit Results](./P2_6_SECURITY_AUDIT_COMPLETE.md)
- [API Documentation](./API_DOCUMENTATION_COMPLETE.md)

## Support

For Auth0-related issues:
- Auth0 Dashboard: https://manage.auth0.com/
- Auth0 Documentation: https://auth0.com/docs
- Platform Security: See `docs/SECURITY.md`
