# Security Package Documentation

## Overview

The Cineca Agentic Platform security package provides comprehensive security controls for authentication, authorization, audit logging, data protection, and access control. The package is designed with a modular architecture that supports enterprise-grade security requirements while maintaining developer-friendly APIs.

## Architecture

The security package is organized into several key modules:

- **`__init__.py`** - Lazy import facade providing unified access to all security functions
- **`auth.py`** - JWT token creation, validation, and password hashing utilities
- **`authorization.py`** - Role-based access control with scope expansion and policy enforcement
- **`audit.py`** - Structured security event logging with provenance integration
- **`pii_scrubber.py`** - Personally identifiable information detection and redaction
- **`rate_limit.py`** - Request rate limiting with Redis/memory backends
- **`jwt.py`** - OIDC JWT validation with JWKS caching and principal extraction
- **`perm.py`** - Permission checking and enforcement utilities
- **`validators.py`** - Input validation and sanitization helpers
- **`tenants.py`** - Multi-tenancy support with tenant isolation
- **`admin.py`** - Administrative permission enforcement
- **`secrets.py`** - Secret management and validation
- **`output_guard.py`** - Output filtering and Cypher query safety guards

## Core Security Features

### Authentication (`auth.py`)

The authentication module provides JWT-based authentication with secure password handling:

```python
from src.security import create_access_token, hash_password, verify_password

# Create JWT token
token = create_access_token({"sub": "user123", "scopes": ["read:profile"]})

# Password hashing
hashed = hash_password("user_password")
is_valid = verify_password("user_password", hashed)
```

**Key Features:**
- JWT token creation with configurable expiration
- Secure password hashing using bcrypt via passlib
- Demo authenticator for development/testing
- Configurable token TTL and issuer validation

### Authorization (`authorization.py`)

Role-based access control with flexible scope matching:

```python
from src.security import check_scopes, authorize_or_403, require_scopes

# Check if user has required scopes
user_scopes = ["user:profile", "tools:basic"]
required = ["user:profile"]
authorize_or_403(user_scopes, required)

# FastAPI dependency
@router.get("/protected")
async def protected_endpoint(user = Depends(require_scopes(["user:profile"]))):
    return {"message": "Access granted"}
```

**Key Features:**
- YAML-based policy configuration
- Wildcard scope pattern matching (`tools:*` matches `tools:basic`)
- Role-to-scope expansion
- FastAPI dependency injection integration

### Audit Logging (`audit.py`)

Comprehensive security event logging with structured data:

```python
from src.security import audit_event, audit_auth_success

# Log authentication success
audit_auth_success(
    subject="user123",
    method="password",
    ip_address="192.168.1.1",
    user_agent="Mozilla/5.0..."
)

# Log custom security events
audit_event(
    event_type="policy_decision",
    subject="user123",
    action="access_denied",
    resource="admin:panel",
    reason="insufficient_permissions"
)
```

**Key Features:**
- Structured logging with provenance tracking
- Prometheus metrics integration
- Configurable log levels and filtering
- Security event correlation and analysis

### PII Scrubbing (`pii_scrubber.py`)

Automatic detection and redaction of sensitive information:

```python
from src.security import scrub_text, find_pii

# Scrub sensitive data from text
clean_text = scrub_text("User email: john@example.com, SSN: 123-45-6789")

# Find all PII in text
pii_matches = find_pii("Contact: john@example.com, Card: 4111-1111-1111-1111")
```

**Key Features:**
- Multiple redaction modes: mask, hash, remove
- Comprehensive PII pattern detection (emails, SSNs, credit cards, etc.)
- Luhn algorithm validation for financial data
- Recursive scrubbing of nested data structures

### Rate Limiting (`rate_limit.py`)

Request rate limiting with multiple backend options:

```python
from src.security import rate_limiter

# FastAPI dependency with rate limiting
@router.get("/api/data")
async def rate_limited_endpoint(
    request: Request,
    user = Depends(rate_limiter(limit=100, window_seconds=3600))
):
    return {"data": "rate limited response"}
```

**Key Features:**
- Fixed-window rate limiting algorithm
- Redis backend for distributed environments
- In-memory fallback for single-instance deployments
- Configurable limits and window sizes

### JWT Validation (`jwt.py`)

OIDC-compliant JWT validation with JWKS caching:

```python
from src.security import validate_jwt, get_current_principal

# Validate JWT token
claims = await validate_jwt("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...")

# FastAPI dependency for authenticated requests
@router.get("/protected")
async def protected_endpoint(principal = Depends(get_current_principal)):
    return {"user": principal.sub, "scopes": list(principal.scopes)}
```

**Key Features:**
- JWKS key caching and rotation
- Signature verification with multiple algorithms
- Time-based validation (exp, nbf, iat)
- Principal extraction with scope normalization

### Permission Management (`perm.py`)

Permission-based access control with role mapping:

```python
from src.security import has_perms, require_perms, current_permissions

# Check user permissions
user = {"permissions": ["tools:basic", "user:me"]}
has_basic_tools = has_perms(user, "tools:basic")

# FastAPI dependency
@router.get("/tools")
async def tools_endpoint(user = Depends(require_perms("tools:basic"))):
    return {"tools": "available"}
```

**Key Features:**
- Permission extraction from JWT claims
- Role-to-permission mapping (admin role → admin:all)
- Auth0-style permission claim support
- Flexible permission checking with any-of logic

### Input Validation (`validators.py`)

Comprehensive input validation and sanitization:

```python
from src.security import ensure_str, ensure_int, validate_pagination

# Validate and sanitize inputs
username = ensure_str(request.username, min_len=3, max_len=50)
limit, offset = validate_pagination(request.limit, request.offset)

# Multi-field validation with error collection
data = validate_fields([
    ("username", lambda: ensure_str(body.get("username"), min_len=3)),
    ("email", lambda: ensure_str(body.get("email"), pattern=r".+@.+\..+")),
])
```

**Key Features:**
- Type coercion and validation
- Length and pattern constraints
- Pagination and sorting validation
- Query cost estimation and limits
- Structured error reporting

### Multi-Tenancy (`tenants.py`)

Tenant isolation and context management:

```python
from src.security import require_tenant, get_current_tenant, tenantize_key

# FastAPI dependency for tenant enforcement
@router.get("/data")
async def tenant_endpoint(
    tenant: str = Depends(require_tenant()),
    data = Depends(get_current_tenant())
):
    return {"tenant": tenant, "data": get_cached_data(cache_key)}
```

**Key Features:**
- Header and query parameter tenant extraction
- Configurable allowlists and defaults
- Context variable-based tenant propagation
- Cache/DB key namespacing

### Administrative Controls (`admin.py`)

Admin permission enforcement utilities:

```python
from src.security import require_admin, is_admin

# Check admin status
if is_admin(principal):
    # Allow admin operations
    pass

# FastAPI dependency
@router.delete("/users/{user_id}")
async def delete_user(user_id: str, admin = Depends(require_admin())):
    # Only admins can delete users
    delete_user_record(user_id)
```

### Secret Management (`secrets.py`)

Secure secret handling and validation:

```python
from src.security import validate_secrets_on_startup, install_log_masking

# Validate secrets on startup
summary = validate_secrets_on_startup(settings)
if not summary["ok"]:
    raise ValueError(f"Secret validation failed: {summary['errors']}")

# Install log masking for sensitive data
install_log_masking()
```

**Key Features:**
- Secret validation with environment-specific rules
- Automatic log masking for sensitive data
- Secure secret generation utilities
- Production vs development validation modes

### Output Guard (`output_guard.py`)

Query and output safety controls:

```python
from src.security import guard_cypher, analyze_cypher

# Analyze Cypher query safety
analysis = analyze_cypher("MATCH (n) RETURN n LIMIT 10")
if analysis.risk_score > 50:
    # High-risk query detected
    pass

# Guard Cypher execution
result = guard_cypher(
    "MATCH (n)-[*]->(m) RETURN n, m",  # Potentially unbounded
    mode="enforce",
    enforce_limit=True
)
safe_query = result.sanitized_query  # Will have LIMIT appended
```

**Key Features:**
- Cypher query analysis and risk scoring
- Automatic LIMIT injection for unbounded queries
- Write operation blocking
- Destructive operation prevention

## Configuration

The security package reads configuration from the main settings object. Key configuration options include:

```python
# Authentication
JWT_SECRET = "your-secret-key"
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Authorization
AUTHORIZATION_POLICY_FILE = "config/auth_policy.yaml"

# Rate Limiting
RATE_LIMIT_BACKEND = "redis"  # or "memory"
RATE_LIMIT_REDIS_URL = "redis://localhost:6379"

# Multi-tenancy
TENANCY_ENABLED = True
TENANT_HEADER = "X-Tenant-Id"
TENANCY_ALLOWED = ["tenant1", "tenant2"]

# Output Guard
OUTPUT_GUARD_MODE = "enforce"  # "monitor", "off"
OUTPUT_GUARD_ALLOW_WRITES = False
OUTPUT_GUARD_DEFAULT_LIMIT = 100

# Audit Logging
AUDIT_LOG_LEVEL = "INFO"
AUDIT_PROMETHEUS_ENABLED = True
```

## Integration Examples

### FastAPI Application Setup

```python
from fastapi import FastAPI, Depends, Request
from src.security import (
    get_current_principal, require_scopes, require_tenant,
    rate_limiter, validate_secrets_on_startup
)

app = FastAPI()

# Validate secrets on startup
@app.on_event("startup")
async def startup_event():
    validate_secrets_on_startup(settings)

# Protected endpoints
@app.get("/api/profile")
async def get_profile(
    principal = Depends(get_current_principal),
    tenant = Depends(require_tenant())
):
    return {
        "user": principal.sub,
        "tenant": tenant,
        "scopes": list(principal.scopes)
    }

@app.get("/api/admin")
async def admin_panel(
    request: Request,
    admin = Depends(require_admin()),
    _ = Depends(rate_limiter(limit=10, window_seconds=60))
):
    return {"message": "Admin access granted"}
```

### Middleware Integration

```python
from src.security import install_log_masking, audit_middleware

# Install security middleware
app.middleware("http")(audit_middleware)
install_log_masking()  # Mask sensitive data in logs
```

## Security Best Practices

1. **Always validate secrets on startup** in production environments
2. **Use HTTPS** for all API communications
3. **Implement proper rate limiting** to prevent abuse
4. **Enable audit logging** for security monitoring
5. **Configure tenant isolation** for multi-tenant deployments
6. **Use output guards** for generated queries and content
7. **Regularly rotate secrets** and monitor for suspicious activity
8. **Validate all inputs** using the provided validators
9. **Implement proper error handling** without leaking sensitive information

## Testing

The security package includes comprehensive test coverage. Run tests with:

```bash
# Run all security tests
pytest tests/security/

# Run specific test files
pytest tests/security/test_auth.py
pytest tests/security/test_authorization.py
pytest tests/security/test_jwt.py
```

## Dependencies

- `python-jose[cryptography]` - JWT handling and cryptography
- `passlib[bcrypt]` - Password hashing
- `httpx` - HTTP client for JWKS fetching
- `redis` - Redis client for distributed rate limiting
- `structlog` - Structured logging
- `prometheus-client` - Metrics collection
- `pyyaml` - YAML policy file parsing

## API Reference

### Authentication Functions
- `create_access_token(data: dict) -> str`
- `decode_access_token(token: str) -> dict`
- `hash_password(password: str) -> str`
- `verify_password(password: str, hashed: str) -> bool`

### Authorization Functions
- `check_scopes(user_scopes: list, required: list, mode: str = "any") -> bool`
- `authorize_or_403(user_scopes: list, required: list, mode: str = "any") -> None`
- `require_scopes(required) -> FastAPI dependency`

### JWT Functions
- `validate_jwt(token: str) -> dict`
- `get_current_principal(token: str) -> Principal`
- `require_scopes(required) -> FastAPI dependency`

### Permission Functions
- `current_permissions(user) -> set[str]`
- `has_perms(user, any_of) -> bool`
- `enforce_perms(user, any_of) -> None`
- `require_perms(any_of) -> FastAPI dependency`

### Validation Functions
- `ensure_str(value, **kwargs) -> str`
- `ensure_int(value, **kwargs) -> int`
- `validate_pagination(limit, offset) -> tuple[int, int]`
- `validate_fields(specs) -> dict`

### Tenant Functions
- `require_tenant() -> FastAPI dependency`
- `get_current_tenant() -> str | None`
- `tenantize_key(key: str, tenant: str | None) -> str`

### Security Utilities
- `scrub_text(text: str, mode: str = "mask") -> str`
- `rate_limiter(limit: int, window_seconds: int) -> FastAPI dependency`
- `audit_event(**kwargs) -> None`
- `guard_cypher(query: str, **kwargs) -> OutputGuardResult`

For detailed API documentation, see the docstrings in each module.</content>
<parameter name="filePath">/Users/armanfeili/Arman/Sapienza Courses/4-semester/Thesis/ILP-Thesis-2025/Cineca-Agentic-Platform/README_security.md