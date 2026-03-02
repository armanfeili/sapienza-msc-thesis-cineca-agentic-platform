# Security Framework

The security package provides comprehensive authentication, authorization, auditing, and data protection capabilities for the Cineca Agentic Platform. It implements a defense-in-depth approach with multiple security layers and graceful degradation when components are unavailable.

## Architecture Overview

The security framework follows these core principles:

- **Lazy Loading**: Components imported only when needed to minimize startup overhead
- **Dependency Tolerance**: Graceful degradation when security dependencies unavailable
- **Comprehensive Auditing**: All security events logged with tamper-evident provenance
- **Multi-Tenant Support**: Tenant-aware access control and data isolation
- **Type Safety**: Pydantic models for all security data structures
- **Performance Focused**: Minimal overhead for common operations

## Core Components

### 1. Authentication (`auth.py`, `jwt.py`)

JWT-based authentication with OIDC integration and password hashing.

#### JWT Authentication
- **Token Creation**: Signed JWT tokens with configurable expiration
- **Token Validation**: Bearer token validation with scope extraction
- **Principal Context**: User identity and permissions from JWT claims
- **Multi-Tenant**: Tenant-aware token payloads

#### Password Security
- **BCrypt Hashing**: Industry-standard password hashing
- **Verification**: Secure password verification with timing attack protection

#### Key Models
```python
class TokenPayload(BaseModel):
    sub: str | None = None
    scopes: list[str] = Field(default_factory=list)
    exp: int | None = None
    tid: str | None = None  # Tenant ID
    extra: dict[str, Any] = Field(default_factory=dict)

class UserInfo(BaseModel):
    username: str
    scopes: list[str] = Field(default_factory=list)
    tenant_id: str | None = None
```

### 2. Authorization (`authorization.py`, `perm.py`)

Role-based and permission-based access control with RBAC support.

#### Permission System
- **Auth0-Style Permissions**: Granular permission strings (`tools:basic`, `admin:all`)
- **Role Mapping**: Automatic permission assignment based on roles
- **Scope Validation**: OAuth2 scope checking
- **Admin Privileges**: Implicit admin permissions for admin roles

#### Authorization Decisions
```python
class AuthzDecision:
    ALLOW = "allow"
    DENY = "deny"
    UNKNOWN = "unknown"
```

#### Permission Checking
```python
from src.security import has_perms, require_perms

# Check permissions
if has_perms(user, any_of=["tools:basic", "admin:all"]):
    # Allow access
    pass

# FastAPI dependency
@router.get("/protected")
async def protected_endpoint(user = require_perms(["tools:basic"])):
    return {"message": "Access granted"}
```

### 3. Auditing (`audit.py`)

Comprehensive security event logging with tamper-evident provenance.

#### Audit Events
- **Authentication**: Login success/failure events
- **Authorization**: Access decisions and policy evaluations
- **Rate Limiting**: Throttling events and violations
- **Model Usage**: LLM API call tracking
- **Data Access**: Database and file access logging

#### Audit Event Structure
```python
@dataclass
class AuditEvent:
    event_id: str
    timestamp: datetime
    category: str  # "auth", "access", "policy", etc.
    action: str    # "login", "query", "modify", etc.
    outcome: str   # "success", "failure", "denied"
    severity: str  # "info", "warning", "error", "critical"
    user_id: str | None = None
    tenant_id: str | None = None
    resource: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    content_hash: str | None = None
```

#### Usage
```python
from src.security import audit_auth_success, audit_access

# Audit successful authentication
audit_auth_success(
    user_id="user123",
    tenant_id="tenant456",
    method="password"
)

# Audit resource access
audit_access(
    user_id="user123",
    resource="/api/tools",
    action="invoke",
    outcome="allowed"
)
```

### 4. Input Validation (`validators.py`)

Comprehensive input validation and sanitization utilities.

#### Validation Types
- **Type Enforcement**: String, int, float, bool, list, dict validation
- **Identifier Validation**: Safe identifier checking
- **Pagination**: Page/size parameter validation
- **Sorting**: Sort field and direction validation
- **Query Cost**: Database query cost estimation
- **Result Limits**: Response size limiting

#### HTTP Validation
```python
from src.security import validate_pagination, raise_http_422

# Validate pagination parameters
page, size = validate_pagination(
    page=request.query_params.get("page"),
    size=request.query_params.get("size")
)

# Raise HTTP 422 for validation errors
raise_http_422("Invalid input", issues=[{"field": "email", "message": "Invalid format"}])
```

### 5. Intent Filtering (`intent_filter.py`)

Security-focused intent analysis for user request classification.

#### Intent Analysis
- **Pattern Matching**: Regex-based security pattern detection
- **Context Analysis**: User role and tenant context consideration
- **Risk Assessment**: Automatic risk scoring for requests
- **Policy Enforcement**: Intent-based access control

#### Intent Results
```python
class IntentResult:
    intent: str
    confidence: float
    risk_level: str  # "low", "medium", "high", "critical"
    requires_approval: bool
    blocked_reasons: list[str]
```

### 6. Output Guard (`output_guard.py`)

Response sanitization and security filtering.

#### Cypher Query Protection
- **Query Analysis**: AST-based Cypher query parsing
- **Injection Prevention**: SQL injection detection for graph queries
- **Limit Enforcement**: Automatic LIMIT clause addition
- **Schema Validation**: Safe schema operation checking

#### Text Content Filtering
- **PII Detection**: Personal identifiable information scrubbing
- **Content Classification**: Sensitive content identification
- **Sanitization**: Safe content transformation

#### Usage
```python
from src.security import guard_cypher, guard_text

# Validate Cypher query
result = guard_cypher(
    query="MATCH (n) RETURN n LIMIT 100",
    user_permissions=["read:basic"]
)

if result.allowed:
    # Execute query safely
    execute_cypher(result.sanitized_query)
```

### 7. PII Scrubbing (`pii_scrubber.py`)

Personal identifiable information detection and removal.

#### PII Detection
- **Pattern Matching**: Email, phone, SSN, credit card detection
- **Context Analysis**: Surrounding text analysis for accuracy
- **Custom Patterns**: Configurable PII detection rules
- **False Positive Reduction**: Confidence scoring

#### Scrubbing Modes
```python
from src.security import scrub_text, contains_pii

# Check for PII
if contains_pii(text):
    # Scrub sensitive information
    safe_text = scrub_text(text, replacement="[REDACTED]")
```

### 8. Rate Limiting (`rate_limit.py`)

Distributed rate limiting with Redis backend.

#### Rate Limit Types
- **User-Based**: Per-user request throttling
- **Tenant-Based**: Organization-level quotas
- **Endpoint-Based**: API-specific limits
- **Sliding Window**: Time-based rate calculation

#### Rate Limit Results
```python
class RateLimitResult:
    allowed: bool
    remaining: int
    reset_time: datetime
    retry_after: int | None = None
```

#### Usage
```python
from src.security import rate_limiter

# Check rate limit
result = await rate_limiter.check(
    key="user:123",
    limit=100,
    window_seconds=3600
)

if result.allowed:
    # Process request
    process_request()
else:
    # Return rate limit exceeded
    raise HTTPException(429, headers={"Retry-After": str(result.retry_after)})
```

### 9. Multi-Tenancy (`tenants.py`)

Tenant isolation and context management.

#### Tenant Context
```python
class TenantContext:
    tenant_id: str
    tenant_name: str
    isolation_level: str  # "shared", "dedicated", "isolated"
    quotas: dict[str, Any]
    features: set[str]
```

#### Context Management
```python
from src.security import set_current_tenant, require_tenant

# Set tenant context
set_current_tenant("tenant123")

# FastAPI dependency
@router.get("/tenant-data")
async def tenant_endpoint(tenant = require_tenant()):
    # Access tenant-specific data
    return get_tenant_data(tenant.tenant_id)
```

### 10. Policy Management (`policies_loader.py`)

Dynamic policy loading and role-based access control.

#### Policy Bundle
```python
class PolicyBundle:
    roles: dict[str, dict[str, Any]]
    scopes: dict[str, list[str]]
    permissions: dict[str, list[str]]
    policies: dict[str, dict[str, Any]]
```

#### Policy Loading
```python
from src.security import get_bundle, get_roles

# Load current policies
bundle = get_bundle()

# Get available roles
roles = get_roles()

# Check role scopes
scopes = get_scopes_for_role("admin")
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `JWT_SECRET_KEY` | Required | JWT signing key |
| `JWT_ALGORITHM` | `HS256` | JWT algorithm |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Token expiration time |
| `RATE_LIMIT_REDIS_URL` | `redis://localhost:6379` | Rate limit Redis URL |
| `AUDIT_LOG_LEVEL` | `INFO` | Audit logging level |
| `PII_SCRUB_ENABLED` | `true` | Enable PII scrubbing |

### Policy Configuration

Policies are loaded from YAML/JSON files with the following structure:

```yaml
roles:
  admin:
    permissions: ["admin:all", "tools:all"]
    scopes: ["read", "write", "admin"]
  user:
    permissions: ["tools:basic", "user:me"]
    scopes: ["read"]

policies:
  tool_access:
    effect: allow
    principals: ["role:user"]
    actions: ["tools:invoke"]
    conditions:
      - tenant_match: true
```

## Usage Examples

### Complete Authentication Flow
```python
from src.security import (
    create_access_token,
    validate_jwt,
    require_perms,
    audit_auth_success
)

# Create token
token = create_access_token(
    subject="user123",
    scopes=["tools:basic"],
    tenant_id="tenant456"
)

# Validate in endpoint
@router.get("/protected")
async def protected_endpoint(
    user = require_perms(["tools:basic"]),
    token: str = Depends(validate_jwt)
):
    audit_auth_success(user.user_id, user.tenant_id)
    return {"message": "Authenticated and authorized"}
```

### Comprehensive Request Security
```python
from src.security import (
    require_tenant,
    rate_limiter,
    guard_cypher,
    scrub_text,
    audit_access
)

@router.post("/query")
async def execute_query(
    request: QueryRequest,
    tenant = require_tenant(),
    user = require_perms(["tools:basic"])
):
    # Rate limiting
    rate_result = await rate_limiter.check(f"user:{user.user_id}")
    if not rate_result.allowed:
        raise HTTPException(429)

    # Input validation
    validate_query_cost(request.query)

    # Cypher security
    guard_result = guard_cypher(request.query, user.permissions)
    if not guard_result.allowed:
        audit_access(user.user_id, "cypher", "blocked")
        raise HTTPException(403, "Query not allowed")

    # Execute query
    result = await execute_cypher(guard_result.sanitized_query)

    # Output scrubbing
    safe_result = scrub_text(str(result))

    audit_access(user.user_id, "cypher", "allowed")
    return {"result": safe_result}
```

## Security Event Monitoring

### Audit Event Categories
- **auth**: Authentication events (login, logout, token operations)
- **access**: Authorization decisions and resource access
- **policy**: Policy evaluation and enforcement
- **rate_limit**: Rate limiting events and violations
- **model_usage**: LLM API calls and usage tracking
- **data_access**: Database and file system access

### Metrics Integration
Security events are automatically tracked via Prometheus metrics:
- `security_audit_events_total`: Total audit events by category and severity
- `rate_limit_checks_total`: Rate limit evaluation counts
- `auth_attempts_total`: Authentication attempt tracking

## Performance Considerations

- **Lazy Imports**: Security modules loaded only when first accessed
- **Caching**: Policy and tenant data cached in Redis where applicable
- **Async Operations**: All I/O operations are async to prevent blocking
- **Minimal Overhead**: Fast-path operations avoid expensive checks when possible
- **Connection Pooling**: Database and Redis connections are pooled

## Compliance and Standards

### Security Standards
- **OAuth2/OIDC**: Industry-standard authentication protocols
- **JWT RFC 7519**: Secure token format compliance
- **BCrypt**: NIST-recommended password hashing
- **RBAC**: Role-based access control patterns

### Data Protection
- **PII Detection**: Comprehensive personal data identification
- **Content Filtering**: Sensitive information sanitization
- **Audit Trails**: Tamper-evident security event logging
- **Encryption**: Secure credential and token handling

### Compliance Features
- **GDPR**: Data minimization and consent management
- **SOX**: Audit trail and access control requirements
- **HIPAA**: Protected health information handling
- **PCI DSS**: Payment data protection

## Troubleshooting

### Common Issues

1. **Authentication Failures**
   - Verify JWT_SECRET_KEY configuration
   - Check token expiration times
   - Validate OIDC provider configuration

2. **Authorization Denies**
   - Review user roles and permissions
   - Check policy file syntax
   - Verify tenant context

3. **Rate Limiting**
   - Confirm Redis connectivity
   - Check rate limit configuration
   - Monitor Redis memory usage

4. **Audit Gaps**
   - Verify logging configuration
   - Check provenance service availability
   - Review audit event filtering

### Debug Mode

Enable detailed security logging:
```bash
export SECURITY_DEBUG=true
export AUDIT_LOG_LEVEL=DEBUG
```

### Health Checks

Security subsystem health can be verified via:
- Authentication endpoint responsiveness
- Policy file loading status
- Redis/cache connectivity
- Audit log writing capability</content>
<parameter name="filePath">/Users/armanfeili/Arman/Sapienza Courses/4-semester/Thesis/ILP-Thesis-2025/Cineca-Agentic-Platform/docs/general/README_security.md