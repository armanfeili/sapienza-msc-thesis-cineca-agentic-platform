# Admin Tenant Management Endpoints

Complete documentation for all tenant administration endpoints.

---

## 1. List All Tenants

**GET /v1/admin/tenants** – Retrieve all tenants in the platform

### Why we need this endpoint:

- **Platform visibility**: Admins need to see all tenant organizations using the system
- **Monitoring and auditing**: Track which tenants are active, when they joined, and their configuration
- **Resource management**: Understanding tenant count helps with capacity planning
- **Without this**: Admins would have no way to discover what tenants exist or audit the platform

### What it does:

- Fetches a paginated list of all registered tenants
- Returns tenant details including ID, name, contact email, metadata, and timestamps
- Supports efficient caching to reduce server load on repeated requests
- Handles large tenant lists through pagination (doesn't load everything at once)

### Access:

- **Who can call it**: Platform administrators only
- **Required permission**: `admin:all` scope
- **Authentication**: Bearer token with admin privileges

### Behavior:

- **Pagination**: 
  - Default page size: 100 tenants
  - Maximum page size: 1,000 tenants
  - Use `page_size` and `page_token` query parameters to navigate
  - Returns `next_page_token` when more results are available
- **Caching**:
  - Sends `ETag` header with every response
  - Client can send `If-None-Match` header to check if data changed
  - Returns `304 Not Modified` when cached data is still valid (saves bandwidth)
- **Backend behavior**: Works with both Redis and in-memory storage (same functionality)

### Responses:

- **200 OK**: Successfully retrieved tenant list (may be empty if no tenants exist)
- **304 Not Modified**: Your cached copy is still current (no new data sent)
- **401 Unauthorized**: Missing or invalid authentication token
- **403 Forbidden**: Your account doesn't have admin privileges

### Examples:

```bash
# Get first page of tenants (default 100 items)
curl -X GET "http://localhost:8000/v1/admin/tenants" \
     -H "Authorization: Bearer $ADMIN_TOKEN"

# Get 50 tenants per page
curl -X GET "http://localhost:8000/v1/admin/tenants?page_size=50" \
     -H "Authorization: Bearer $ADMIN_TOKEN"

# Get next page using token from previous response
curl -X GET "http://localhost:8000/v1/admin/tenants?page_size=100&page_token=eyJvZmZzZXQiOjEwMH0" \
     -H "Authorization: Bearer $ADMIN_TOKEN"

# Use caching to avoid unnecessary data transfer
curl -X GET "http://localhost:8000/v1/admin/tenants" \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "If-None-Match: \"page-hash-abc123\""
```

---

## 2. Create New Tenant

**POST /v1/admin/tenants** – Register a new tenant organization

### Why we need this endpoint:

- **Onboarding**: New organizations need to be added to the platform
- **Multi-tenancy**: Each organization gets isolated resources and configuration
- **Access control**: Tenants serve as security boundaries for data and permissions
- **Without this**: No way to add new organizations or manage multi-tenant architecture

### What it does:

- Creates a new tenant record with a server-generated unique ID
- Validates tenant information (name, admin email, optional metadata)
- Records creation in audit logs for compliance
- Prevents duplicate creation with smart idempotency handling
- Returns the complete tenant object including the generated ID

### Access:

- **Who can call it**: Platform administrators only
- **Required permission**: `admin:all` scope
- **Authentication**: Bearer token with admin privileges
- **Audit header**: `X-Tenant-Id` header tracks which admin tenant performed the action (defaults to `tenant-admin-root`)

### Behavior:

- **Idempotency**:
  - If tenant with same ID already exists with identical data → Returns `200 OK` (safe retry)
  - If tenant with same ID exists but different data → Returns `409 Conflict` (prevents accidental overwrites)
- **Validation**:
  - Name: Required, 1-255 characters
  - Admin email: Required, must be valid email format (RFC 5322)
  - Metadata: Optional, any JSON object structure allowed
- **Backend behavior**: Works with both Redis and in-memory storage (same functionality)

### Responses:

- **201 Created**: Tenant successfully created, includes `Location` header with tenant URL
- **200 OK**: Tenant already exists with same configuration (idempotent success)
- **401 Unauthorized**: Missing or invalid authentication token
- **403 Forbidden**: Your account doesn't have admin privileges
- **409 Conflict**: Tenant ID already exists with different configuration
- **422 Unprocessable Entity**: Validation failed (invalid email, missing required fields, etc.)

### Examples:

```bash
# Create minimal tenant (only required fields)
curl -X POST "http://localhost:8000/v1/admin/tenants" \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -H "X-Tenant-Id: tenant-admin-root" \
     -d '{
       "name": "ACME Corporation",
       "admin_email": "admin@example.com"
     }'

# Create tenant with custom metadata
curl -X POST "http://localhost:8000/v1/admin/tenants" \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "ACME Corporation",
       "admin_email": "admin@example.com",
       "metadata": {
         "region": "us-east-1",
         "tier": "premium",
         "contact": {
           "slack": "#acme-admins",
           "phone": "+1-555-0100"
         },
         "features": ["a", "b", "c"]
       }
     }'

# Note: X-Tenant-Id header is optional, defaults to "tenant-admin-root"
curl -X POST "http://localhost:8000/v1/admin/tenants" \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"name": "Test Tenant", "admin_email": "test@example.com"}'
```

---

## 3. Get Tenant Details

**GET /v1/admin/tenants/{tenant_id}** – Look up a specific tenant by ID

### Why we need this endpoint:

- **Detail inspection**: Admins need to view complete information about a specific tenant
- **Troubleshooting**: When investigating issues, you need to check tenant configuration
- **Verification**: Confirm tenant settings before making changes
- **Without this**: No way to retrieve a specific tenant's current state or verify their details

### What it does:

- Retrieves complete information for a single tenant using their unique ID
- Returns all tenant fields: name, admin email, metadata, creation date, last update
- Provides ETag for caching (useful if checking the same tenant repeatedly)
- Fast lookup by ID (no need to paginate through entire tenant list)

### Access:

- **Who can call it**: Platform administrators only
- **Required permission**: `admin:all` scope
- **Authentication**: Bearer token with admin privileges

### Behavior:

- **Caching**: 
  - Returns `ETag` header for cache validation
  - Client can use `If-None-Match` for conditional requests
- **Backend behavior**: Works with both Redis and in-memory storage (same functionality)

### Responses:

- **200 OK**: Tenant found and details returned
- **401 Unauthorized**: Missing or invalid authentication token
- **403 Forbidden**: Your account doesn't have admin privileges
- **404 Not Found**: No tenant exists with that ID

### Examples:

```bash
# Get specific tenant by ID
curl -X GET "http://localhost:8000/v1/admin/tenants/tenant-501a149f" \
     -H "Authorization: Bearer $ADMIN_TOKEN"

# Check if tenant data changed (conditional request)
curl -X GET "http://localhost:8000/v1/admin/tenants/tenant-501a149f" \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "If-None-Match: \"tenant-abc123\""
```

---

## 4. Update Tenant Information

**PATCH /v1/admin/tenants/{tenant_id}** – Modify existing tenant details

### Why we need this endpoint:

- **Configuration changes**: Tenants need their settings updated as requirements evolve
- **Contact updates**: Admin email addresses change when personnel switch roles
- **Metadata management**: Tenant metadata grows as you add features (regions, tiers, contact info)
- **Without this**: Tenants would be immutable after creation, requiring delete/recreate for any change

### What it does:

- Updates one or more fields of an existing tenant
- Supports partial updates (only send the fields you want to change)
- Intelligently merges metadata (adds new keys, updates existing ones, preserves others)
- Records the change in audit logs for compliance
- Returns the updated tenant object

### Access:

- **Who can call it**: Platform administrators only
- **Required permission**: `admin:all` scope
- **Authentication**: Bearer token with admin privileges
- **Audit header**: `X-Tenant-Id` header tracks which admin tenant performed the update (defaults to `tenant-admin-root`)

### Behavior:

- **Partial updates**:
  - Only include fields you want to change
  - Omitted fields remain unchanged
  - Empty request body is rejected (must update at least one field)
- **Metadata merging**:
  - New metadata keys are added
  - Existing keys are updated with new values
  - Keys not in the request are preserved
  - Nested objects are recursively merged (not replaced wholesale)
  - Set a key to `null` to remove it
- **Backend behavior**: Works with both Redis and in-memory storage (same functionality)

### Responses:

- **200 OK**: Tenant updated successfully, returns updated tenant object
- **400 Bad Request**: Empty request body (you must provide at least one field to update)
- **401 Unauthorized**: Missing or invalid authentication token
- **403 Forbidden**: Your account doesn't have admin privileges
- **404 Not Found**: No tenant exists with that ID
- **422 Unprocessable Entity**: Validation failed (e.g., invalid email format)

### Examples:

```bash
# Update just the tenant name
curl -X PATCH "http://localhost:8000/v1/admin/tenants/tenant-501a149f" \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -H "X-Tenant-Id: tenant-admin-root" \
     -d '{
       "name": "ACME Corp (Updated)"
     }'

# Update admin email only
curl -X PATCH "http://localhost:8000/v1/admin/tenants/tenant-501a149f" \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "admin_email": "newadmin@example.com"
     }'

# Add/update metadata fields (merges with existing)
curl -X PATCH "http://localhost:8000/v1/admin/tenants/tenant-501a149f" \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "metadata": {
         "tier": "enterprise",
         "support_plan": "premium"
       }
     }'

# Update multiple fields at once
curl -X PATCH "http://localhost:8000/v1/admin/tenants/tenant-501a149f" \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "ACME Global Corporation",
       "admin_email": "global-admin@example.com",
       "metadata": {
         "region": "global",
         "tier": "enterprise"
       }
     }'
```

---

## 5. Delete Tenant

**DELETE /v1/admin/tenants/{tenant_id}** – Remove a tenant from the platform

### Why we need this endpoint:

- **Offboarding**: Organizations leave the platform or contracts end
- **Cleanup**: Remove test tenants or duplicates
- **Compliance**: Some regulations require ability to delete customer data
- **Without this**: Tenants would accumulate forever, no way to clean up or remove organizations

### What it does:

- Removes the tenant record from the platform
- Checks for dependencies (jobs, providers, etc.) before deletion
- Prevents accidental data loss by blocking deletion of tenants with active resources
- Records the deletion in audit logs for compliance
- Returns no content on success (HTTP 204)

### Access:

- **Who can call it**: Platform administrators only
- **Required permission**: `admin:all` scope
- **Authentication**: Bearer token with admin privileges
- **Audit header**: `X-Tenant-Id` header tracks which admin tenant performed the deletion (defaults to `tenant-admin-root`)

### Behavior:

- **Dependency checking**:
  - System checks if tenant has any associated resources (jobs, providers, agent runs, etc.)
  - If dependencies exist → Returns `409 Conflict` with details about blockers
  - If no dependencies → Deletion proceeds
- **Safety policy**:
  - Prevents accidental deletion of active tenants
  - You must clean up tenant's resources before deleting the tenant itself
- **Not idempotent**: Deleting non-existent tenant returns `404 Not Found` (not `204 No Content`)
- **Backend behavior**: Works with both Redis and in-memory storage (same functionality)

### Responses:

- **204 No Content**: Tenant successfully deleted (empty response body)
- **401 Unauthorized**: Missing or invalid authentication token
- **403 Forbidden**: Your account doesn't have admin privileges
- **404 Not Found**: No tenant exists with that ID
- **409 Conflict**: Tenant has dependent resources (jobs, providers, etc.) that must be deleted first

### Examples:

```bash
# Delete a tenant (only works if no dependencies)
curl -X DELETE "http://localhost:8000/v1/admin/tenants/tenant-501a149f" \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "X-Tenant-Id: tenant-admin-root"

# Attempt to delete tenant with dependencies (will fail with 409)
curl -X DELETE "http://localhost:8000/v1/admin/tenants/tenant-with-jobs" \
     -H "Authorization: Bearer $ADMIN_TOKEN"
# Response: 409 Conflict with details about blocking resources

# Note: X-Tenant-Id header is optional, defaults to "tenant-admin-root"
curl -X DELETE "http://localhost:8000/v1/admin/tenants/tenant-test-123" \
     -H "Authorization: Bearer $ADMIN_TOKEN"
```

---

## Common Headers

All endpoints support these standard headers:

### Request Headers:
- `Authorization: Bearer <token>` – **Required** for authentication
- `X-Tenant-Id: <tenant-id>` – **Optional** for audit context (POST/PATCH/DELETE only, defaults to `tenant-admin-root`)
- `If-None-Match: "<etag>"` – **Optional** for conditional requests (GET only)

### Response Headers:
- `X-Request-Id` – Correlation ID for tracking requests across logs
- `X-Event-Id` – Provenance/audit event ID (write operations only)
- `X-Trace-Id` – Distributed tracing ID
- `ETag` – Entity tag for caching (GET operations)
- `Location` – URL to created resource (POST 201 only)

---

## Authentication & Authorization

All admin tenant endpoints require:

1. **Valid JWT token** in `Authorization` header
2. **admin:all scope** in the token's scope claim
3. Parent router (`/v1/admin`) enforces this globally

Without these, you'll receive:
- `401 Unauthorized` – Missing or invalid token
- `403 Forbidden` – Token valid but missing admin:all scope

---

## Error Response Format (RFC 7807)

All errors follow RFC 7807 Problem Details format:

```json
{
  "type": "https://example.com/probs/not-found",
  "title": "Not Found",
  "status": 404,
  "detail": "Tenant 'tenant-xyz' not found",
  "instance": "/v1/admin/tenants/tenant-xyz",
  "extensions": {
    "correlation_id": "req_1a2b3c4d",
    "timestamp": "2025-10-11T10:30:00Z"
  }
}
```

---

## Best Practices

1. **Use pagination** for large tenant lists (don't request 1000+ tenants at once)
2. **Cache responses** using ETags to reduce server load
3. **Include X-Tenant-Id** in write operations for better audit trails
4. **Check dependencies** before deletion to avoid 409 conflicts
5. **Use partial updates** (PATCH) instead of full replacements
6. **Store correlation IDs** (X-Request-Id) for troubleshooting

---

**Last updated**: October 11, 2025
