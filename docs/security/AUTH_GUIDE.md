# Authentication Guide: OIDC & Tenancy 🔐

**Goal**: Set up production authentication with your own Identity Provider (IdP) in **less than 15 minutes**.

This guide covers:
- OIDC/OAuth2 configuration with Auth0, Okta, Azure AD, or any OIDC provider
- Scopes and permissions matrix
- Multi-tenancy setup
- Sample JWTs and testing

---

## Table of Contents

1. [Overview](#overview)
2. [Quick Setup (Auth0)](#quick-setup-auth0)
3. [Generic OIDC Setup](#generic-oidc-setup)
4. [Scopes & Permissions Matrix](#scopes--permissions-matrix)
5. [Multi-Tenancy](#multi-tenancy)
6. [Sample JWTs](#sample-jwts)
7. [Testing Authentication](#testing-authentication)
8. [Troubleshooting](#troubleshooting)

---

## Overview

The Cineca Agentic Platform uses **OpenID Connect (OIDC)** for authentication with **Role-Based Access Control (RBAC)** for authorization.

### Architecture

```
┌─────────────┐      ┌──────────────┐      ┌─────────────────┐
│   Client    │─────▶│  Your IdP    │─────▶│  Cineca API     │
│   (Browser/ │      │  (Auth0/     │      │  (Validates     │
│    API)     │      │   Okta/etc)  │      │   JWT tokens)   │
└─────────────┘      └──────────────┘      └─────────────────┘
                           │                        │
                           │ Issues JWT             │ Checks:
                           │ with claims            │ - Signature
                           │                        │ - Expiration
                           └────────────────────────│ - Scopes
                                                    │ - Roles
```

### Key Concepts

- **OIDC**: Standard protocol for authentication (built on OAuth2)
- **JWT**: JSON Web Token containing user identity and claims
- **Scopes**: OAuth2 scopes (e.g., `openid`, `profile`, `email`)
- **Roles**: Application-level roles (e.g., `viewer`, `operator`, `admin`)
- **Permissions**: Fine-grained permissions (e.g., `read:agents`, `write:workflows`)
- **Tenancy**: Isolation of data per organization/tenant

---

## Quick Setup (Auth0)

**Time**: ~10 minutes

### Prerequisites

- Auth0 account (free tier works)
- Docker and Docker Compose installed

### Step 1: Create Auth0 Application (3 minutes)

1. **Login to Auth0**: Go to https://auth0.com and sign in

2. **Create Application**:
   - Navigate to **Applications → Create Application**
   - Name: `Cineca Agentic Platform`
   - Type: **Machine to Machine Applications** (for API access)
   - Click **Create**

3. **Configure Application**:
   - Note your **Domain** (e.g., `your-tenant.auth0.com`)
   - Note your **Client ID**
   - Note your **Client Secret**
   - Set **Allowed Callback URLs**: `http://localhost:8080/callback`
   - Set **Allowed Logout URLs**: `http://localhost:8080`
   - Click **Save Changes**

### Step 2: Create Auth0 API (2 minutes)

1. **Create API**:
   - Navigate to **Applications → APIs → Create API**
   - Name: `Cineca Agentic Platform API`
   - Identifier: `https://api.cineca-platform.local` (can be any URL)
   - Signing Algorithm: **RS256**
   - Click **Create**

2. **Configure Permissions**:
   - Go to **Permissions** tab
   - Add these scopes:

   | Scope | Description |
   |-------|-------------|
   | `read:agents` | Read agent definitions |
   | `write:agents` | Create/update/delete agents |
   | `run:agents` | Execute agent runs |
   | `read:workflows` | Read workflow definitions |
   | `write:workflows` | Create/update/delete workflows |
   | `read:users` | Read user information |
   | `write:users` | Manage users |
   | `admin:all` | Full administrative access |

3. **Authorize Application**:
   - Go to **Machine to Machine Applications** tab
   - Toggle **ON** for your application
   - Select all scopes
   - Click **Update**

### Step 3: Create Roles (2 minutes)

1. **Create Roles**:
   - Navigate to **User Management → Roles → Create Role**
   - Create these roles:

   **Viewer Role**:
   - Name: `viewer`
   - Description: Read-only access to agents and workflows
   - Permissions: `read:agents`, `read:workflows`

   **Operator Role**:
   - Name: `operator`
   - Description: Can read and execute agents/workflows
   - Permissions: `read:agents`, `read:workflows`, `run:agents`

   **Admin Role**:
   - Name: `admin`
   - Description: Full administrative access
   - Permissions: `admin:all` (or all individual permissions)

### Step 4: Create Test User (1 minute)

1. **Create User**:
   - Navigate to **User Management → Users → Create User**
   - Email: `test@example.com`
   - Password: `Test123!@#` (change this!)
   - Click **Create**

2. **Assign Role**:
   - Open the user
   - Go to **Roles** tab
   - Assign **operator** role
   - Click **Assign**

### Step 5: Configure Platform (2 minutes)

1. **Create `.env` file**:

```bash
# Create .env file
cat > .env << EOF
# Auth0 Configuration
AUTH0_DOMAIN=your-tenant.auth0.com
AUTH0_CLIENT_ID=your-client-id-here
AUTH0_CLIENT_SECRET=your-client-secret-here
AUTH0_AUDIENCE=https://api.cineca-platform.local

# JWT Configuration
JWT_ALGORITHM=RS256
JWT_ISSUER=https://your-tenant.auth0.com/

# Database
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/cineca
REDIS_URL=redis://redis:6379
MEMGRAPH_HOST=memgraph
MEMGRAPH_PORT=7687

# LLM Providers (optional for testing)
OPENAI_API_KEY=sk-your-key-here
EOF
```

2. **Start Services**:

```bash
# Start all services
docker-compose up -d

# Wait for services to be ready
sleep 30

# Check health
curl http://localhost:8080/health
```

**Expected Output**:

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "auth": {
    "provider": "auth0",
    "domain": "your-tenant.auth0.com"
  }
}
```

✅ If you see `"status": "healthy"`, your Auth0 integration is working!

---

## Generic OIDC Setup

**Time**: ~15 minutes

This section covers setup with **any OIDC-compliant IdP** (Okta, Azure AD, Keycloak, Google, etc.).

### Prerequisites

- OIDC provider account
- Admin access to create applications
- OIDC discovery endpoint (e.g., `https://your-idp.com/.well-known/openid-configuration`)

### Step 1: Register Application (5 minutes)

#### For Okta:

1. **Create Application**:
   - Sign in to Okta Admin Console
   - Navigate to **Applications → Create App Integration**
   - Sign-in method: **OIDC - OpenID Connect**
   - Application type: **Web Application**
   - Click **Next**

2. **Configure Application**:
   - App integration name: `Cineca Agentic Platform`
   - Grant type: **Client Credentials**, **Authorization Code**
   - Sign-in redirect URIs: `http://localhost:8080/callback`
   - Sign-out redirect URIs: `http://localhost:8080`
   - Controlled access: Choose access level
   - Click **Save**

3. **Note Credentials**:
   - Client ID
   - Client Secret
   - Okta domain (e.g., `dev-12345.okta.com`)

#### For Azure AD:

1. **Create App Registration**:
   - Sign in to Azure Portal
   - Navigate to **Azure Active Directory → App registrations → New registration**
   - Name: `Cineca Agentic Platform`
   - Supported account types: **Single tenant**
   - Redirect URI: `Web` → `http://localhost:8080/callback`
   - Click **Register**

2. **Create Client Secret**:
   - Go to **Certificates & secrets → New client secret**
   - Description: `Cineca API Key`
   - Expires: **24 months**
   - Click **Add**
   - **Copy the secret immediately** (you won't see it again!)

3. **Configure API Permissions**:
   - Go to **API permissions → Add a permission**
   - Select **Microsoft Graph**
   - Add: `User.Read`, `openid`, `profile`, `email`
   - Click **Grant admin consent**

4. **Note Credentials**:
   - Application (client) ID
   - Directory (tenant) ID
   - Client secret value

#### For Keycloak:

1. **Create Client**:
   - Sign in to Keycloak Admin Console
   - Select your realm
   - Navigate to **Clients → Create**
   - Client ID: `cineca-platform`
   - Client Protocol: **openid-connect**
   - Click **Save**

2. **Configure Client**:
   - Access Type: **confidential**
   - Valid Redirect URIs: `http://localhost:8080/callback`
   - Click **Save**

3. **Get Client Secret**:
   - Go to **Credentials** tab
   - Copy **Secret**

4. **Note Credentials**:
   - Client ID
   - Client Secret
   - Keycloak URL (e.g., `http://keycloak:8080/auth`)
   - Realm name

### Step 2: Configure Scopes (3 minutes)

Each OIDC provider has different mechanisms for defining scopes:

#### Auth0:
- Define scopes in **API → Permissions** tab

#### Okta:
- Navigate to **Security → API → Scopes**
- Add custom scopes for your app

#### Azure AD:
- Navigate to **App registrations → Expose an API**
- Add scopes under **Scopes defined by this API**

#### Keycloak:
- Navigate to **Client Scopes**
- Create new scopes or use predefined ones

**Recommended Scopes**:

```
openid              # Required for OIDC
profile             # User profile information
email               # User email address
read:agents         # Read agent definitions
write:agents        # Create/update/delete agents
run:agents          # Execute agent runs
read:workflows      # Read workflow definitions
write:workflows     # Create/update/delete workflows
admin:all           # Full administrative access
```

### Step 3: Configure Roles (3 minutes)

#### Auth0:
- Use **Authorization Extension** or **Core Authorization**
- Create roles and assign permissions

#### Okta:
- Navigate to **Directory → Groups**
- Create groups: `viewer`, `operator`, `admin`
- Assign users to groups
- Map groups to claims in token

#### Azure AD:
- Navigate to **App registrations → App roles**
- Create roles with allowed member types: **Users/Groups**

#### Keycloak:
- Navigate to **Roles**
- Create realm or client roles
- Assign roles to users

**Recommended Roles**:

| Role | Permissions |
|------|-------------|
| `viewer` | `read:agents`, `read:workflows` |
| `operator` | `read:agents`, `read:workflows`, `run:agents` |
| `admin` | All permissions or `admin:all` |

### Step 4: Configure Platform (4 minutes)

Create a `.env` file with your OIDC provider configuration:

#### Generic OIDC Configuration:

```bash
# OIDC Configuration
OIDC_DISCOVERY_URL=https://your-idp.com/.well-known/openid-configuration
OIDC_CLIENT_ID=your-client-id
OIDC_CLIENT_SECRET=your-client-secret
OIDC_AUDIENCE=https://api.cineca-platform.local

# JWT Configuration
JWT_ALGORITHM=RS256
JWT_ISSUER=https://your-idp.com/

# Claim Mapping (optional - customize based on your IdP)
JWT_ROLES_CLAIM=roles                    # Where to find roles in JWT
JWT_PERMISSIONS_CLAIM=permissions        # Where to find permissions in JWT
JWT_TENANT_CLAIM=org_id                  # Where to find tenant ID in JWT
JWT_EMAIL_CLAIM=email                    # Where to find email in JWT
JWT_NAME_CLAIM=name                      # Where to find name in JWT

# Database
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/cineca
REDIS_URL=redis://redis:6379
MEMGRAPH_HOST=memgraph
MEMGRAPH_PORT=7687
```

#### Okta-Specific:

```bash
AUTH0_DOMAIN=dev-12345.okta.com
AUTH0_CLIENT_ID=0oa1ab2cd3ef4gh5ij6k
AUTH0_CLIENT_SECRET=your-client-secret
AUTH0_AUDIENCE=api://cineca-platform
JWT_ISSUER=https://dev-12345.okta.com/oauth2/default
```

#### Azure AD-Specific:

```bash
AUTH0_DOMAIN=login.microsoftonline.com/your-tenant-id
AUTH0_CLIENT_ID=your-application-id
AUTH0_CLIENT_SECRET=your-client-secret
AUTH0_AUDIENCE=api://cineca-platform
JWT_ISSUER=https://login.microsoftonline.com/your-tenant-id/v2.0
JWT_ALGORITHM=RS256
JWT_ROLES_CLAIM=roles
```

#### Keycloak-Specific:

```bash
AUTH0_DOMAIN=keycloak.example.com/auth/realms/your-realm
AUTH0_CLIENT_ID=cineca-platform
AUTH0_CLIENT_SECRET=your-client-secret
AUTH0_AUDIENCE=cineca-platform
JWT_ISSUER=http://keycloak:8080/auth/realms/your-realm
JWT_ROLES_CLAIM=realm_access.roles
```

---

## Scopes & Permissions Matrix

### Standard OIDC Scopes

| Scope | Description | Claims Returned |
|-------|-------------|-----------------|
| `openid` | Required for OIDC | `sub` (subject identifier) |
| `profile` | User profile data | `name`, `family_name`, `given_name`, `picture` |
| `email` | User email address | `email`, `email_verified` |
| `address` | User postal address | `address` object |
| `phone` | User phone number | `phone_number`, `phone_number_verified` |

### Cineca Platform Scopes

| Scope | Description | Roles |
|-------|-------------|-------|
| `read:agents` | Read agent definitions | viewer, operator, admin |
| `write:agents` | Create/update/delete agents | operator, admin |
| `run:agents` | Execute agent runs | operator, admin |
| `read:workflows` | Read workflow definitions | viewer, operator, admin |
| `write:workflows` | Create/update/delete workflows | operator, admin |
| `read:users` | Read user information | admin |
| `write:users` | Manage users | admin |
| `read:metrics` | View metrics and analytics | operator, admin |
| `write:tools` | Manage tool policies | admin |
| `admin:all` | Full administrative access | admin |

### Role-to-Permission Mapping

#### Viewer Role

**Purpose**: Read-only access for monitoring and auditing

**Permissions**:
- ✅ `read:agents` — View agent definitions
- ✅ `read:workflows` — View workflow definitions
- ❌ Cannot create, update, delete, or run agents
- ❌ Cannot access admin endpoints

**Use Cases**:
- Auditors reviewing agent configurations
- Stakeholders monitoring agent activity
- Read-only dashboard viewers

#### Operator Role

**Purpose**: Day-to-day operations and agent execution

**Permissions**:
- ✅ `read:agents` — View agent definitions
- ✅ `write:agents` — Create/update/delete agents
- ✅ `run:agents` — Execute agent runs
- ✅ `read:workflows` — View workflow definitions
- ✅ `write:workflows` — Create/update/delete workflows
- ✅ `read:metrics` — View metrics
- ❌ Cannot manage users or system settings

**Use Cases**:
- Data scientists creating and running agents
- Engineers building workflows
- Operations team executing agents

#### Admin Role

**Purpose**: Full system administration

**Permissions**:
- ✅ `admin:all` — All permissions
- ✅ `read:users`, `write:users` — User management
- ✅ `write:tools` — Tool policy management
- ✅ All operator permissions
- ✅ All viewer permissions

**Use Cases**:
- Platform administrators
- Security teams managing access
- DevOps configuring system settings

### API Endpoint → Permission Mapping

| Endpoint | Method | Required Permission | Role |
|----------|--------|---------------------|------|
| `/api/v1/agents` | GET | `read:agents` | viewer, operator, admin |
| `/api/v1/agents` | POST | `write:agents` | operator, admin |
| `/api/v1/agents/{id}` | GET | `read:agents` | viewer, operator, admin |
| `/api/v1/agents/{id}` | PUT | `write:agents` | operator, admin |
| `/api/v1/agents/{id}` | DELETE | `write:agents` | operator, admin |
| `/api/v1/agents/{id}/run` | POST | `run:agents` | operator, admin |
| `/api/v1/workflows` | GET | `read:workflows` | viewer, operator, admin |
| `/api/v1/workflows` | POST | `write:workflows` | operator, admin |
| `/api/v1/users` | GET | `read:users` | admin |
| `/api/v1/users` | POST | `write:users` | admin |
| `/api/v1/metrics` | GET | `read:metrics` | operator, admin |
| `/api/v1/admin/*` | ANY | `admin:all` | admin |

---

## Multi-Tenancy

The platform supports **multi-tenancy** to isolate data between organizations.

### Tenancy Models

#### 1. Organization-Based Tenancy (Recommended)

Each organization gets isolated data:
- Separate agents per org
- Separate workflows per org
- Separate users per org
- Shared infrastructure

**JWT Claim**:
```json
{
  "org_id": "org_abc123",
  "org_name": "Acme Corporation"
}
```

**Configuration**:
```bash
# .env
JWT_TENANT_CLAIM=org_id
ENABLE_MULTI_TENANCY=true
```

#### 2. User-Based Tenancy

Each user sees only their own data:
- Agents created by user
- Workflows created by user
- No sharing between users

**JWT Claim**:
```json
{
  "sub": "user_xyz789"
}
```

**Configuration**:
```bash
# .env
JWT_TENANT_CLAIM=sub
ENABLE_MULTI_TENANCY=true
TENANCY_MODEL=user
```

#### 3. Single-Tenant

All users share the same data (suitable for small teams):

**Configuration**:
```bash
# .env
ENABLE_MULTI_TENANCY=false
```

### Setting Up Tenancy

#### Step 1: Configure IdP to Include Tenant Claim

**Auth0**:

1. Create **Action** (Rules → Actions → Build Custom):

```javascript
exports.onExecutePostLogin = async (event, api) => {
  // Get organization from user metadata
  const orgId = event.user.app_metadata?.org_id || 'default';
  const orgName = event.user.app_metadata?.org_name || 'Default Org';
  
  // Add to token
  api.accessToken.setCustomClaim('org_id', orgId);
  api.accessToken.setCustomClaim('org_name', orgName);
};
```

2. Deploy and add to Login flow

**Okta**:

1. Navigate to **Security → API → Authorization Servers**
2. Edit your authorization server
3. Add **Claim**:
   - Name: `org_id`
   - Include in: `Access Token`
   - Value type: `Expression`
   - Value: `user.orgId`

**Azure AD**:

1. Navigate to **App registrations → Token configuration**
2. Add **Optional claim**:
   - Token type: `Access`
   - Claim: `extension_orgId`
3. Ensure user extension attribute exists

**Keycloak**:

1. Navigate to **Client Scopes → Create**
2. Add **Mapper**:
   - Mapper Type: `User Attribute`
   - User Attribute: `orgId`
   - Token Claim Name: `org_id`
   - Claim JSON Type: `String`

#### Step 2: Configure Platform

```bash
# .env
JWT_TENANT_CLAIM=org_id
ENABLE_MULTI_TENANCY=true
```

#### Step 3: Create Users with Tenant IDs

**Auth0**:

```bash
# Set user metadata via Management API
curl -X PATCH https://your-tenant.auth0.com/api/v2/users/auth0|user-id \
  -H "Authorization: Bearer MGMT_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "app_metadata": {
      "org_id": "org_abc123",
      "org_name": "Acme Corporation"
    }
  }'
```

**Okta**:

```bash
# Set custom attribute via Users API
curl -X POST https://dev-12345.okta.com/api/v1/users/user-id \
  -H "Authorization: SSWS your-api-token" \
  -H "Content-Type: application/json" \
  -d '{
    "profile": {
      "orgId": "org_abc123"
    }
  }'
```

### Tenancy Examples

#### Example 1: Organization Isolation

**Scenario**: Two organizations using the same platform

**Org A Token**:
```json
{
  "sub": "user_alice",
  "email": "alice@acme.com",
  "org_id": "org_acme",
  "roles": ["operator"]
}
```

**Org B Token**:
```json
{
  "sub": "user_bob",
  "email": "bob@globex.com",
  "org_id": "org_globex",
  "roles": ["operator"]
}
```

**Result**:
- Alice can only see agents/workflows for `org_acme`
- Bob can only see agents/workflows for `org_globex`
- No data leakage between organizations

#### Example 2: Hierarchical Tenancy

**Scenario**: Parent-child organization structure

**Parent Org Admin Token**:
```json
{
  "sub": "user_admin",
  "org_id": "org_parent",
  "org_hierarchy": ["org_parent", "org_child1", "org_child2"],
  "roles": ["admin"]
}
```

**Child Org User Token**:
```json
{
  "sub": "user_child",
  "org_id": "org_child1",
  "roles": ["operator"]
}
```

**Result**:
- Parent admin can see all orgs (parent + children)
- Child user can only see their org (`org_child1`)

---

## Sample JWTs

### Viewer Role JWT (Read-Only)

**Decoded**:

```json
{
  "header": {
    "alg": "RS256",
    "typ": "JWT",
    "kid": "key-id-123"
  },
  "payload": {
    "sub": "auth0|viewer-user-id",
    "name": "Jane Viewer",
    "email": "jane@example.com",
    "email_verified": true,
    "iss": "https://your-tenant.auth0.com/",
    "aud": "https://api.cineca-platform.local",
    "iat": 1698400000,
    "exp": 1698486400,
    "azp": "your-client-id",
    "scope": "openid profile email read:agents read:workflows",
    "roles": ["viewer"],
    "permissions": ["read:agents", "read:workflows"],
    "org_id": "org_example"
  },
  "signature": "..."
}
```

**Encoded**:

```
eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6ImtleS1pZC0xMjMifQ.eyJzdWIiOiJhdXRoMHx2aWV3ZXItdXNlci1pZCIsIm5hbWUiOiJKYW5lIFZpZXdlciIsImVtYWlsIjoiamFuZUBleGFtcGxlLmNvbSIsImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJpc3MiOiJodHRwczovL3lvdXItdGVuYW50LmF1dGgwLmNvbS8iLCJhdWQiOiJodHRwczovL2FwaS5jaW5lY2EtcGxhdGZvcm0ubG9jYWwiLCJpYXQiOjE2OTg0MDAwMDAsImV4cCI6MTY5ODQ4NjQwMCwiYXpwIjoieW91ci1jbGllbnQtaWQiLCJzY29wZSI6Im9wZW5pZCBwcm9maWxlIGVtYWlsIHJlYWQ6YWdlbnRzIHJlYWQ6d29ya2Zsb3dzIiwicm9sZXMiOlsidmlld2VyIl0sInBlcm1pc3Npb25zIjpbInJlYWQ6YWdlbnRzIiwicmVhZDp3b3JrZmxvd3MiXSwib3JnX2lkIjoib3JnX2V4YW1wbGUifQ.signature
```

**Permissions**:
- ✅ Can read agents
- ✅ Can read workflows
- ❌ Cannot create/update/delete
- ❌ Cannot run agents

### Operator Role JWT

**Decoded**:

```json
{
  "header": {
    "alg": "RS256",
    "typ": "JWT",
    "kid": "key-id-123"
  },
  "payload": {
    "sub": "auth0|operator-user-id",
    "name": "John Operator",
    "email": "john@example.com",
    "email_verified": true,
    "iss": "https://your-tenant.auth0.com/",
    "aud": "https://api.cineca-platform.local",
    "iat": 1698400000,
    "exp": 1698486400,
    "azp": "your-client-id",
    "scope": "openid profile email read:agents write:agents run:agents read:workflows write:workflows",
    "roles": ["operator"],
    "permissions": [
      "read:agents",
      "write:agents",
      "run:agents",
      "read:workflows",
      "write:workflows"
    ],
    "org_id": "org_example"
  },
  "signature": "..."
}
```

**Permissions**:
- ✅ Can read agents/workflows
- ✅ Can create/update/delete agents/workflows
- ✅ Can run agents
- ❌ Cannot manage users
- ❌ Cannot access admin endpoints

### Admin Role JWT

**Decoded**:

```json
{
  "header": {
    "alg": "RS256",
    "typ": "JWT",
    "kid": "key-id-123"
  },
  "payload": {
    "sub": "auth0|admin-user-id",
    "name": "Alice Admin",
    "email": "alice@example.com",
    "email_verified": true,
    "iss": "https://your-tenant.auth0.com/",
    "aud": "https://api.cineca-platform.local",
    "iat": 1698400000,
    "exp": 1698486400,
    "azp": "your-client-id",
    "scope": "openid profile email admin:all",
    "roles": ["admin"],
    "permissions": ["admin:all"],
    "org_id": "org_example"
  },
  "signature": "..."
}
```

**Permissions**:
- ✅ Full access to all endpoints
- ✅ Can manage users
- ✅ Can configure system settings
- ✅ Can access admin endpoints

---

## Testing Authentication

### Step 1: Get an Access Token

#### Using Client Credentials (Machine-to-Machine):

```bash
# Auth0
curl -X POST https://your-tenant.auth0.com/oauth/token \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "your-client-id",
    "client_secret": "your-client-secret",
    "audience": "https://api.cineca-platform.local",
    "grant_type": "client_credentials"
  }'
```

**Response**:
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "token_type": "Bearer",
  "expires_in": 86400
}
```

#### Using Authorization Code (User Login):

1. **Redirect user to login**:

```
https://your-tenant.auth0.com/authorize?
  response_type=code&
  client_id=your-client-id&
  redirect_uri=http://localhost:8080/callback&
  scope=openid profile email read:agents run:agents&
  audience=https://api.cineca-platform.local
```

2. **Exchange code for token**:

```bash
curl -X POST https://your-tenant.auth0.com/oauth/token \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "your-client-id",
    "client_secret": "your-client-secret",
    "code": "authorization-code-from-callback",
    "redirect_uri": "http://localhost:8080/callback",
    "grant_type": "authorization_code"
  }'
```

### Step 2: Decode and Inspect Token

```bash
# Save token
export TOKEN="eyJhbGciOiJSUzI1NiIs..."

# Decode token (using jwt.io or jq)
echo $TOKEN | cut -d '.' -f 2 | base64 -d | jq .
```

**Check**:
- ✅ `iss` matches your IdP
- ✅ `aud` matches your API identifier
- ✅ `exp` is in the future
- ✅ `roles` or `permissions` are present

### Step 3: Test API Calls

```bash
# Test read endpoint (viewer, operator, admin)
curl http://localhost:8080/api/v1/agents \
  -H "Authorization: Bearer $TOKEN"

# Test write endpoint (operator, admin only)
curl -X POST http://localhost:8080/api/v1/agents \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "TestAgent",
    "model": "gpt-4"
  }'

# Test run endpoint (operator, admin only)
curl -X POST http://localhost:8080/api/v1/agents/agent_id/run \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "input": "Hello, world!"
  }'

# Test admin endpoint (admin only)
curl http://localhost:8080/api/v1/admin/users \
  -H "Authorization: Bearer $TOKEN"
```

### Step 4: Verify RBAC

Test with different roles to verify permissions:

#### Viewer Token (Read-Only):

```bash
# Should succeed (200 OK)
curl http://localhost:8080/api/v1/agents \
  -H "Authorization: Bearer $VIEWER_TOKEN"

# Should fail (403 Forbidden)
curl -X POST http://localhost:8080/api/v1/agents \
  -H "Authorization: Bearer $VIEWER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Test"}'
```

**Expected**:
```json
{
  "error": "Forbidden",
  "message": "Insufficient permissions. Required: write:agents"
}
```

#### Operator Token:

```bash
# Should succeed (200 OK)
curl -X POST http://localhost:8080/api/v1/agents \
  -H "Authorization: Bearer $OPERATOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Test"}'

# Should fail (403 Forbidden)
curl http://localhost:8080/api/v1/admin/users \
  -H "Authorization: Bearer $OPERATOR_TOKEN"
```

### Step 5: Test Multi-Tenancy

If multi-tenancy is enabled:

```bash
# Create agent with Org A token
curl -X POST http://localhost:8080/api/v1/agents \
  -H "Authorization: Bearer $ORG_A_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "OrgA-Agent"}'

# Try to access with Org B token (should fail or return empty)
curl http://localhost:8080/api/v1/agents \
  -H "Authorization: Bearer $ORG_B_TOKEN"
```

**Expected**: Org B user should NOT see Org A's agent.

---

## Troubleshooting

### Issue: "Invalid JWT signature"

**Cause**: Platform can't verify JWT signature

**Solutions**:

1. **Check JWKS endpoint**:

```bash
# Verify JWKS endpoint is accessible
curl https://your-tenant.auth0.com/.well-known/jwks.json
```

2. **Check JWT algorithm**:

```bash
# Ensure JWT_ALGORITHM matches (usually RS256)
echo "JWT_ALGORITHM=RS256" >> .env
```

3. **Check issuer**:

```bash
# Ensure JWT_ISSUER matches token's "iss" claim
# Decode token and check "iss" field
echo $TOKEN | cut -d '.' -f 2 | base64 -d | jq .iss
```

### Issue: "Token expired"

**Cause**: JWT exp claim is in the past

**Solutions**:

1. **Get fresh token**:

```bash
# Request new token from IdP
curl -X POST https://your-tenant.auth0.com/oauth/token \
  -d '{"client_id":"...","client_secret":"...","grant_type":"client_credentials"}'
```

2. **Check token expiration**:

```bash
# Decode and check "exp" claim
echo $TOKEN | cut -d '.' -f 2 | base64 -d | jq .exp

# Compare with current time (Unix timestamp)
date +%s
```

### Issue: "Insufficient permissions"

**Cause**: User role doesn't have required permission

**Solutions**:

1. **Check user role**:

```bash
# Decode token and check "roles" or "permissions"
echo $TOKEN | cut -d '.' -f 2 | base64 -d | jq .roles
```

2. **Assign role in IdP**:
   - Auth0: User Management → Users → Roles
   - Okta: Directory → People → Groups
   - Azure AD: Users → Assigned roles

3. **Check permission mapping**:

```bash
# Verify role has required permissions in IdP
# See "Scopes & Permissions Matrix" section above
```

### Issue: "Tenant isolation not working"

**Cause**: JWT doesn't contain tenant claim

**Solutions**:

1. **Check JWT contains tenant claim**:

```bash
# Decode token and check for "org_id" or configured tenant claim
echo $TOKEN | cut -d '.' -f 2 | base64 -d | jq .org_id
```

2. **Configure IdP to include claim**:
   - See "Setting Up Tenancy" section above
   - Create rule/action to add org_id to token

3. **Check platform configuration**:

```bash
# Ensure platform is configured to read tenant claim
cat .env | grep JWT_TENANT_CLAIM
# Should output: JWT_TENANT_CLAIM=org_id
```

### Issue: "CORS errors in browser"

**Cause**: Browser blocking cross-origin requests

**Solutions**:

1. **Enable CORS in platform**:

```bash
# Add to .env
CORS_ALLOWED_ORIGINS=http://localhost:3000,https://your-app.com
```

2. **Include credentials in request**:

```javascript
// Frontend code
fetch('http://localhost:8080/api/v1/agents', {
  headers: {
    'Authorization': `Bearer ${token}`
  },
  credentials: 'include'
})
```

---

## Production Checklist

Before going to production:

### Security

- [ ] Use HTTPS (not HTTP) for all endpoints
- [ ] Rotate client secrets regularly (every 90 days)
- [ ] Enable MFA for admin users
- [ ] Use strong JWT signing algorithm (RS256, not HS256)
- [ ] Set appropriate token expiration (1 hour for access tokens)
- [ ] Implement refresh token rotation
- [ ] Enable rate limiting on auth endpoints
- [ ] Monitor failed authentication attempts

### Configuration

- [ ] Use production IdP (not dev/test)
- [ ] Configure production callback URLs
- [ ] Set up proper CORS origins
- [ ] Use environment-specific secrets
- [ ] Enable audit logging
- [ ] Configure session timeout
- [ ] Set up backup IdP (for disaster recovery)

### Monitoring

- [ ] Monitor authentication success/failure rates
- [ ] Track token expiration errors
- [ ] Alert on unusual authentication patterns
- [ ] Monitor JWKS endpoint availability
- [ ] Track permission denial rates

### Documentation

- [ ] Document auth flow for your team
- [ ] Provide sample tokens for testing
- [ ] Document role-to-permission mapping
- [ ] Create troubleshooting runbook
- [ ] Document disaster recovery for auth

---

## Next Steps

1. **Test Your Setup**:
   - Run through the [Quickstart Guide](./QUICKSTART.md)
   - Test with different roles (viewer, operator, admin)
   - Verify multi-tenancy isolation

2. **Explore Advanced Features**:
   - [API Documentation](./API_DOCUMENTATION.md)
   - [Agents Quickstart](./AGENTS_QUICKSTART.md)
   - [Workflow Guide](./WORKFLOWS_QUICKSTART.md)

3. **Deploy to Production**:
   - [Deployment Guide](./deployment.md)
   - [Security Best Practices](./SECURITY.md)
   - [Monitoring Guide](./OBSERVABILITY.md)

---

## Additional Resources

- **Auth0 Documentation**: https://auth0.com/docs
- **Okta Documentation**: https://developer.okta.com/docs
- **Azure AD Documentation**: https://docs.microsoft.com/azure/active-directory
- **OIDC Specification**: https://openid.net/connect
- **OAuth2 Specification**: https://oauth.net/2
- **JWT Specification**: https://jwt.io

---

**Questions?** Open an issue on [GitHub](https://github.com/ILP-Thesis-2025/Cineca-Agentic-Platform/issues) or join our [Slack community](https://cineca-platform.slack.com).
