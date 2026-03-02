# Tenant Management API Guide

## Overview

The Tenant Management API provides CRUD operations for managing tenants in the Cineca Agentic Platform. All endpoints require `admin:all` scope and are mounted at `/v1/admin/tenants`.

## Authentication

All requests require a valid JWT token with the `admin:all` scope:

```bash
export ADMIN_TOKEN="your-jwt-token-here"
```

## Endpoints

### 1. Create Tenant

Create a new tenant with server-generated ID.

**Endpoint:** `POST /v1/admin/tenants`

**Required Headers:**
- `Authorization: Bearer <token>`
- `X-Tenant-Id: <context-tenant>` (for audit trail)

**Request Body:**
```json
{
  "name": "ACME Corporation",
  "admin_email": "admin@acme.com",
  "metadata": {
    "region": "us-east-1",
    "tier": "premium"
  }
}
```

**Success Response (201 Created):**
```json
{
  "id": "tenant-501a149f",
  "name": "ACME Corporation",
  "admin_email": "admin@acme.com",
  "metadata": {
    "region": "us-east-1",
    "tier": "premium"
  },
  "created_at": "2025-10-11T08:30:00Z",
  "updated_at": "2025-10-11T08:30:00Z"
}
```

**Response Headers:**
- `Location: /v1/admin/tenants/tenant-501a149f`
- `ETag: "abc123..."`
- `X-Event-Id: evt_...`
- `X-Trace-Id: trace_...`

**Example cURL:**
```bash
curl -X POST "http://localhost:8000/v1/admin/tenants" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "X-Tenant-Id: admin-tenant" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "ACME Corporation",
    "admin_email": "admin@acme.com",
    "metadata": {"region": "us-east-1", "tier": "premium"}
  }'
```

**Idempotency:**
- If a tenant with identical config already exists: returns `200 OK` with existing tenant
- If a tenant exists with different config: returns `409 Conflict`

---

### 2. List Tenants

Retrieve paginated list of all tenants.

**Endpoint:** `GET /v1/admin/tenants`

**Query Parameters:**
- `page_size` (optional): Number of items per page (1-1000, default 100)
- `page_token` (optional): Pagination cursor for next page

**Optional Headers:**
- `If-None-Match: "<etag>"` - Returns `304 Not Modified` if content unchanged

**Success Response (200 OK):**
```json
{
  "items": [
    {
      "id": "tenant-501a149f",
      "name": "ACME Corporation",
      "admin_email": "admin@acme.com",
      "metadata": {"region": "us-east-1"},
      "created_at": "2025-10-11T08:30:00Z",
      "updated_at": "2025-10-11T08:30:00Z"
    }
  ],
  "next_page_token": "eyJvZmZzZXQiOjEwMH0",
  "total": 250
}
```

**Response Headers:**
- `ETag: "page-hash..."`
- `Link: </v1/admin/tenants?page_size=100&page_token=xyz>; rel="next"`

**Example cURL:**
```bash
# First page
curl -X GET "http://localhost:8000/v1/admin/tenants?page_size=50" \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# Next page
curl -X GET "http://localhost:8000/v1/admin/tenants?page_size=50&page_token=xyz" \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# With caching
curl -X GET "http://localhost:8000/v1/admin/tenants" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "If-None-Match: \"page-hash-abc\""
```

---

### 3. Get Tenant by ID

Retrieve a specific tenant by its ID.

**Endpoint:** `GET /v1/admin/tenants/{tenant_id}`

**Success Response (200 OK):**
```json
{
  "id": "tenant-501a149f",
  "name": "ACME Corporation",
  "admin_email": "admin@acme.com",
  "metadata": {"region": "us-east-1", "tier": "premium"},
  "created_at": "2025-10-11T08:30:00Z",
  "updated_at": "2025-10-11T08:30:00Z"
}
```

**Response Headers:**
- `ETag: "tenant-hash..."`

**Error Response (404 Not Found):**
```json
{
  "type": "https://example.com/probs/not-found",
  "title": "Not Found",
  "status": 404,
  "detail": "Tenant 'tenant-xyz' not found",
  "instance": "/v1/admin/tenants/tenant-xyz",
  "extensions": {
    "correlation_id": "req_1a2b3c4d"
  }
}
```

**Example cURL:**
```bash
curl -X GET "http://localhost:8000/v1/admin/tenants/tenant-501a149f" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

---

### 4. Update Tenant (Partial)

Update specific fields of a tenant. Metadata is deep-merged with existing values.

**Endpoint:** `PATCH /v1/admin/tenants/{tenant_id}`

**Request Body (all fields optional):**
```json
{
  "name": "ACME Corporation (Updated)",
  "admin_email": "new-admin@acme.com",
  "metadata": {
    "region": "us-west-2",
    "new_key": "value",
    "removed_key": null
  }
}
```

**Metadata Merge Rules:**
- Existing keys are preserved unless explicitly updated
- New keys from request are added
- Set value to `null` to **remove** a key
- Nested objects are recursively merged

**Example:**

Before PATCH:
```json
{
  "metadata": {
    "region": "us-east-1",
    "tier": "premium",
    "config": {"enabled": true}
  }
}
```

PATCH request:
```json
{
  "metadata": {
    "region": "us-west-2",
    "tier": null,
    "config": {"timeout": 30}
  }
}
```

After PATCH:
```json
{
  "metadata": {
    "region": "us-west-2",
    "config": {"enabled": true, "timeout": 30}
  }
}
```

**Success Response (200 OK):**
```json
{
  "id": "tenant-501a149f",
  "name": "ACME Corporation (Updated)",
  "admin_email": "new-admin@acme.com",
  "metadata": {"region": "us-west-2", "new_key": "value"},
  "created_at": "2025-10-11T08:30:00Z",
  "updated_at": "2025-10-11T10:45:00Z"
}
```

**Response Headers:**
- `ETag: "updated-hash..."`
- `X-Event-Id: evt_...`
- `X-Trace-Id: trace_...`

**Example cURL:**
```bash
curl -X PATCH "http://localhost:8000/v1/admin/tenants/tenant-501a149f" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "ACME Corporation (Updated)",
    "metadata": {"region": "us-west-2", "new_key": "value"}
  }'
```

---

### 5. Delete Tenant

Delete a tenant from the platform.

**Endpoint:** `DELETE /v1/admin/tenants/{tenant_id}`

**Success Response (204 No Content):**
- No response body
- Headers: `X-Event-Id`, `X-Trace-Id`, `X-Request-Id`

**Error Response (409 Conflict) - Has Dependencies:**
```json
{
  "type": "https://example.com/probs/conflict",
  "title": "Conflict",
  "status": 409,
  "detail": "Cannot delete tenant with dependent resources",
  "instance": "/v1/admin/tenants/tenant-501a149f",
  "extensions": {
    "correlation_id": "req_1a2b3c4d",
    "blockers": [
      {"type": "provider", "id": "provider-abc", "name": "OpenAI GPT-4"},
      {"type": "job", "id": "job-xyz", "status": "running"}
    ]
  }
}
```

**Example cURL:**
```bash
curl -X DELETE "http://localhost:8000/v1/admin/tenants/tenant-501a149f" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -i  # Show headers including X-Event-Id
```

---

## Error Responses

All errors follow [RFC 7807 Problem Details](https://tools.ietf.org/html/rfc7807) format:

### 400 Bad Request
```json
{
  "type": "https://example.com/probs/bad-request",
  "title": "Bad Request",
  "status": 400,
  "detail": "X-Tenant-Id header required for tenant creation (audit context)",
  "instance": "/v1/admin/tenants"
}
```

### 401 Unauthorized
```json
{
  "type": "https://example.com/probs/unauthorized",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Missing or invalid authentication token",
  "instance": "/v1/admin/tenants"
}
```

### 403 Forbidden
```json
{
  "type": "https://example.com/probs/forbidden",
  "title": "Forbidden",
  "status": 403,
  "detail": "Requires admin:all scope",
  "instance": "/v1/admin/tenants",
  "extensions": {
    "required_scopes": ["admin:all"],
    "user_scopes": ["user:me"]
  }
}
```

### 404 Not Found
```json
{
  "type": "https://example.com/probs/not-found",
  "title": "Not Found",
  "status": 404,
  "detail": "Tenant 'tenant-xyz' not found",
  "instance": "/v1/admin/tenants/tenant-xyz",
  "extensions": {
    "correlation_id": "req_1a2b3c4d"
  }
}
```

### 409 Conflict
```json
{
  "type": "https://example.com/probs/conflict",
  "title": "Conflict",
  "status": 409,
  "detail": "Tenant already exists with different configuration",
  "instance": "/v1/admin/tenants",
  "extensions": {
    "correlation_id": "req_1a2b3c4d",
    "conflicts": {
      "admin_email": {
        "existing": "old@acme.com",
        "requested": "new@acme.com"
      }
    }
  }
}
```

### 422 Unprocessable Entity (Validation Error)
```json
{
  "type": "https://example.com/probs/validation",
  "title": "Validation Error",
  "status": 422,
  "detail": "Request validation failed",
  "instance": "/v1/admin/tenants",
  "extensions": {
    "correlation_id": "req_1a2b3c4d"
  },
  "errors": [
    {
      "type": "value_error",
      "loc": ["body", "admin_email"],
      "msg": "value is not a valid email address: An email address must have an @-sign.",
      "input": "not-an-email",
      "ctx": {
        "reason": "An email address must have an @-sign."
      }
    }
  ]
}
```

---

## Full CRUD Workflow Example

```bash
#!/bin/bash

# Set admin token
export ADMIN_TOKEN="your-jwt-token"

# 1. Create tenant
TENANT_ID=$(curl -s -X POST "http://localhost:8000/v1/admin/tenants" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "X-Tenant-Id: admin-tenant" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Tenant",
    "admin_email": "test@example.com",
    "metadata": {"env": "staging"}
  }' | jq -r '.id')

echo "Created tenant: $TENANT_ID"

# 2. Get tenant by ID
curl -s -X GET "http://localhost:8000/v1/admin/tenants/$TENANT_ID" \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq .

# 3. List tenants
curl -s -X GET "http://localhost:8000/v1/admin/tenants?page_size=10" \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.items[] | {id, name}'

# 4. Update tenant
curl -s -X PATCH "http://localhost:8000/v1/admin/tenants/$TENANT_ID" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Updated Test Tenant",
    "metadata": {"env": "production", "region": "us-west-2"}
  }' | jq .

# 5. Delete tenant
curl -i -X DELETE "http://localhost:8000/v1/admin/tenants/$TENANT_ID" \
  -H "Authorization: Bearer $ADMIN_TOKEN"

echo "Deleted tenant: $TENANT_ID"
```

---

## Rate Limiting

All endpoints include rate limit headers:

- `RateLimit-Limit`: Maximum requests per window
- `RateLimit-Remaining`: Remaining requests in current window
- `RateLimit-Reset`: Timestamp when limit resets

---

## Caching

### ETag Support

All read endpoints support ETag-based caching:

```bash
# First request - gets ETag
ETAG=$(curl -si "http://localhost:8000/v1/admin/tenants" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  | grep -i etag | cut -d' ' -f2 | tr -d '\r')

# Second request - uses ETag
curl -i "http://localhost:8000/v1/admin/tenants" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "If-None-Match: $ETAG"
# Returns 304 Not Modified if content unchanged
```

---

## Observability

### Provenance Headers

Mutation operations (POST, PATCH, DELETE) include provenance headers:

- `X-Event-Id`: Unique event identifier for audit trail
- `X-Trace-Id`: Distributed tracing ID
- `X-Request-Id`: Request correlation ID (all endpoints)

Example:
```bash
curl -i -X POST "http://localhost:8000/v1/admin/tenants" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "X-Tenant-Id: admin-tenant" \
  -H "Content-Type: application/json" \
  -d '{"name": "Test", "admin_email": "test@example.com"}'

# Response includes:
# X-Event-Id: evt_abc123
# X-Trace-Id: trace_def456
# X-Request-Id: req_xyz789
```

---

## Validation Rules

### Name
- **Required** for creation
- 1-255 characters
- Can contain any valid UTF-8 characters

### Admin Email
- **Required** for creation
- Must be valid RFC 5322 email address
- Canonicalized (lowercase domain) on storage
- Examples: `admin@example.com`, `user+tag@domain.co.uk`

### Metadata
- **Optional** (defaults to empty object)
- Arbitrary keys supported (permissive schema)
- Nested objects allowed
- Deep-merge on PATCH operations
- Set value to `null` to remove keys

---

## Migration Notes

### Breaking Changes from Previous Versions

1. **DELETE status code changed from 200 to 204**
   - Now returns `204 No Content` (no response body)
   - Previously returned `200 OK` with confirmation message

2. **List response envelope**
   - New format: `{items: [...], next_page_token: "...", total: N}`
   - Previously: direct array `[...]`

3. **Timestamp format**
   - Now RFC 3339 with UTC offset: `2025-10-11T08:30:00Z`
   - Previously: ISO 8601 without timezone

4. **X-Tenant-Id header**
   - Now **required** for POST (audit context)
   - Previously optional

5. **Error responses**
   - Now RFC 7807 Problem+JSON format
   - Previously: simple `{"detail": "error message"}`

---

## See Also

- [OpenAPI Specification](../api/openapi.json) - Full API documentation
- [Swagger UI](http://localhost:8000/docs) - Interactive API explorer
- [Security Guide](../docs/security.md) - Authentication and authorization
- [Provider Management](./providers-guide.md) - Managing LLM providers
