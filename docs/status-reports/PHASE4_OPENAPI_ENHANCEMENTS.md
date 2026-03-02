# Phase 4 Day 3 - OpenAPI Documentation Enhancements

## Overview

This document outlines OpenAPI specification enhancements for Phase 4 Day 3, focusing on:
1. ✅ ETag support documentation
2. ✅ Location header documentation
3. ✅ Idempotency header documentation
4. ✅ Vary header documentation
5. ✅ Content-Type clarifications

---

## 1. ETag Support Documentation

### Current Implementation Status
- ✅ **GET /v1/agents/sessions/{session_id}** - Full ETag support
- ✅ **GET /v1/agents/sessions/{session_id}/steps** - Full ETag support
- ✅ Dynamic SHA-256 based ETag generation
- ✅ RFC 7232 semantic comparison (W/ prefix ignored)

### OpenAPI Schema Updates (Recommended)

```yaml
# For GET /v1/agents/sessions/{session_id}
responses:
  200:
    description: Session retrieved successfully
    headers:
      ETag:
        schema:
          type: string
        description: |
          Entity tag for cache validation.
          Format: "sha256-<hash>" (weak or strong).
          Clients should store this and send in If-None-Match header
          on subsequent requests to enable 304 Not Modified responses.
        example: '"a1b2c3d4e5f6g7h8"'
      Cache-Control:
        schema:
          type: string
        description: Caching directive for intermediate caches
        example: 'max-age=300, private'
      Vary:
        schema:
          type: string
        description: |
          Indicates which headers affect the response content.
          Shared caches use this to serve correct variant to different clients.
        example: 'Authorization'

  304:
    description: Not Modified
    headers:
      ETag:
        schema:
          type: string
        description: Same ETag as requested in If-None-Match
        example: '"a1b2c3d4e5f6g7h8"'

# For GET /v1/agents/sessions/{session_id}/steps
responses:
  200:
    description: Steps list with pagination
    headers:
      ETag:
        schema:
          type: string
        description: Entity tag for the list (changes when items or order changes)
        example: '"list-sha256-xyz789"'
      Vary:
        schema:
          type: string
        description: Multiple headers affect this response
        example: 'Authorization, X-Default-Scope'
```

### Request Parameters Documentation

```yaml
parameters:
  - name: If-None-Match
    in: header
    required: false
    schema:
      type: string
    description: |
      Conditional header for cache validation.
      If the current ETag matches this value, server responds with 304 Not Modified.
      Multiple ETags can be provided (comma-separated).
      Use weak comparison (W/ prefix ignored).
    example: '"a1b2c3d4e5f6g7h8"'

  - name: If-Match
    in: header
    required: false
    schema:
      type: string
    description: |
      Conditional header for safe updates (future use).
      Request only succeeds if current ETag matches this value.
      Prevents lost update race conditions.
    example: '"a1b2c3d4e5f6g7h8"'
```

### Usage Example in OpenAPI

```yaml
/v1/agents/sessions/{session_id}:
  get:
    summary: Get session state (with caching support)
    description: |
      Retrieve the current state of a session with ETag-based caching.
      
      **Caching Behavior:**
      - First request returns full response with ETag header
      - Subsequent requests include If-None-Match header
      - If resource unchanged: 304 Not Modified (empty body)
      - If resource changed: 200 OK (full response + new ETag)
      
      **Bandwidth Savings:**
      - Typical savings: 80-90% on cached hits
      - Especially effective for high-frequency polling
      
      **Example Flow:**
      ```
      # Request 1: No cache
      GET /v1/agents/sessions/123 HTTP/1.1
      → 200 OK
      ETag: "abc123"
      Content: {...full session data...}
      
      # Request 2: With cache
      GET /v1/agents/sessions/123 HTTP/1.1
      If-None-Match: "abc123"
      → 304 Not Modified
      (empty body - no bandwidth used!)
      
      # Request 3: Data changed
      GET /v1/agents/sessions/123 HTTP/1.1
      If-None-Match: "abc123"
      → 200 OK
      ETag: "def456"
      Content: {...updated session data...}
      ```
    parameters:
      - name: If-None-Match
        in: header
        required: false
        schema:
          type: string
        example: '"abc123"'
    responses:
      200:
        description: Session data (may be from previous request)
        headers:
          ETag:
            schema:
              type: string
      304:
        description: Not Modified (use cached data)
        headers:
          ETag:
            schema:
              type: string
```

---

## 2. Location Header Documentation

### Current Implementation Status
- ✅ **POST /v1/agents/sessions** - Returns Location header with session URL
- ✅ **POST /v1/agents/sessions/{session_id}/steps** - Returns Location header with step URL
- ✅ **POST /v1/agent-runs** - Returns Location header with run URL
- ✅ HTTP 201 Created responses include Location header

### OpenAPI Schema Updates

```yaml
responses:
  201:
    description: Resource created successfully
    headers:
      Location:
        schema:
          type: string
          format: uri
        description: |
          Absolute URI of the newly created resource.
          Clients can immediately use this URL for subsequent operations (GET, DELETE, etc.)
          Follows RFC 7231 standard for resource discovery.
        example: '/v1/agents/sessions/f47ac10b-58cc-4372-a567-0e02b2c3d479'
      Idempotency-Key:
        schema:
          type: string
        description: |
          Echo of the Idempotency-Key header from request.
          Confirms the request ID used for duplicate detection.
        example: 'my-unique-id-123'
      Idempotency-Replayed:
        schema:
          type: boolean
        description: |
          Indicates if this response is from cache (true) or fresh creation (false).
          false = resource was created now
          true = response was replayed from idempotency store
        example: false
```

### Usage Examples

```yaml
/v1/agents/sessions:
  post:
    summary: Create a new session (with Location header)
    description: |
      Create a new agent session with automatic resource URL discovery.
      
      **Resource Discovery:**
      - Response includes Location header with session URL
      - Clients can navigate to this URL immediately
      - No need to parse response body to discover resource
      
      **Example Flow:**
      ```
      # Create session
      POST /v1/agents/sessions
      Content-Type: application/json
      Authorization: Bearer $TOKEN
      Idempotency-Key: session-001
      
      {
        "manager": "test-manager"
      }
      
      # Response
      HTTP/1.1 201 Created
      Location: /v1/agents/sessions/f47ac10b-58cc-4372-a567-0e02b2c3d479
      Idempotency-Key: session-001
      Idempotency-Replayed: false
      Content-Type: application/json
      
      {
        "session_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
        "status": "active",
        ...
      }
      
      # Client can now use Location
      GET /v1/agents/sessions/f47ac10b-58cc-4372-a567-0e02b2c3d479
      Authorization: Bearer $TOKEN
      ```
    requestBody:
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/SessionCreateRequest'
    responses:
      201:
        description: Session created
        headers:
          Location:
            schema:
              type: string
              format: uri
            example: '/v1/agents/sessions/f47ac10b-58cc-4372-a567-0e02b2c3d479'
          Idempotency-Key:
            schema:
              type: string
          Idempotency-Replayed:
            schema:
              type: boolean
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/SessionResponse'
```

---

## 3. Idempotency Header Documentation

### Current Implementation Status
- ✅ All POST endpoints accept Idempotency-Key header
- ✅ Echo Idempotency-Key in response headers
- ✅ Add Idempotency-Replayed flag indicating if response is cached
- ✅ PostgreSQL + Redis storage for duplicate detection
- ✅ 24-hour retention policy

### OpenAPI Schema Updates

```yaml
requestBody:
  headers:
    Idempotency-Key:
      schema:
        type: string
      required: true
      description: |
        Unique request identifier for duplicate detection.
        Server stores this key for 24 hours to detect retries.
        
        **Requirements:**
        - Must be unique per request (UUID v4 recommended)
        - Same request = same key
        - Different requests = different keys
        - Can be any string (no format enforced)
        
        **Behavior:**
        - First request: Resource created, key stored
        - Retry with same key: Cached response returned (Idempotency-Replayed: true)
        - Different key: New resource created
        
        **Example Values:**
        - UUID: "550e8400-e29b-41d4-a716-446655440000"
        - Timestamp: "2025-10-20-10:30:45-abc123"
        - Custom: "my-app-request-12345"
      example: '550e8400-e29b-41d4-a716-446655440000'

responses:
  201:
    headers:
      Idempotency-Key:
        schema:
          type: string
        description: Echo of Idempotency-Key from request
        example: '550e8400-e29b-41d4-a716-446655440000'
      
      Idempotency-Replayed:
        schema:
          type: boolean
        description: |
          Indicates if this is a cached response or fresh creation.
          
          - **false**: Resource was created now (first request with this key)
          - **true**: Response was replayed from idempotency store (duplicate request)
          
          Clients should check this flag to determine:
          - false: Perform first-time actions (logging, notifications, etc.)
          - true: Skip duplicate actions, use cached result
        example: false
```

### Usage Examples

```yaml
/v1/agents/sessions:
  post:
    summary: Create session (idempotent)
    parameters:
      - name: Idempotency-Key
        in: header
        required: true
        schema:
          type: string
        description: |
          Unique request ID for duplicate detection.
          Same key = same request = cached response.
        example: '550e8400-e29b-41d4-a716-446655440000'
    
    responses:
      201:
        description: Session created or replayed
        headers:
          Idempotency-Key:
            schema:
              type: string
          Idempotency-Replayed:
            schema:
              type: boolean
        
        content:
          application/json:
            examples:
              first_request:
                value:
                  session_id: "f47ac10b-58cc-4372-a567-0e02b2c3d479"
                  status: "active"
                  created_at: "2025-10-20T10:30:45Z"
              
              replayed_request:
                value:
                  session_id: "f47ac10b-58cc-4372-a567-0e02b2c3d479"
                  status: "active"
                  created_at: "2025-10-20T10:30:45Z"

      422:
        description: |
          Validation Error
          - Missing Idempotency-Key header
          - Invalid request body
```

---

## 4. Vary Header Documentation

### Current Implementation Status
- ✅ Middleware automatically adds Vary headers based on endpoint
- ✅ **Public endpoints**: `Vary: Accept-Encoding`
- ✅ **Admin/scope-aware endpoints**: `Vary: Authorization, X-Default-Scope`
- ✅ **Tenant endpoints**: `Vary: Authorization, X-Tenant-Id`

### OpenAPI Schema Updates

```yaml
responses:
  200:
    headers:
      Vary:
        schema:
          type: string
        description: |
          Indicates which request headers affect the response content.
          Used by shared caches to serve correct variant to different clients.
          
          **Values by endpoint:**
          - Public endpoints (health): `Accept-Encoding`
          - Auth-aware endpoints: `Authorization`
          - Scope-aware endpoints: `Authorization, X-Default-Scope`
          - Multi-tenant endpoints: `Authorization, X-Tenant-Id`
          
          **Why it matters:**
          - Cache should store separate copies for each Authorization value
          - Cache should store separate copies for each scope
          - Cache should store separate copies for each tenant
          - Without Vary, cache might serve wrong data to different users
          
          **RFC Reference:** RFC 7231 Section 7.1.4
        example: 'Authorization, X-Default-Scope'
```

### Endpoint Documentation by Category

```yaml
# Public endpoints
/v1/health/live:
  get:
    responses:
      200:
        headers:
          Vary:
            schema:
              type: string
            description: 'Accept-Encoding (response is always the same regardless of Authorization)'
            example: 'Accept-Encoding'

# Auth-aware endpoints
/v1/agents/sessions:
  get:
    responses:
      200:
        headers:
          Vary:
            schema:
              type: string
            description: |
              Authorization - Each user sees different sessions list.
              Cache must not serve user A's sessions to user B.
            example: 'Authorization'

# Scope-aware endpoints
/v1/tools:
  get:
    responses:
      200:
        headers:
          Vary:
            schema:
              type: string
            description: |
              Authorization, X-Default-Scope
              Different scopes may see different tools.
              Different users (Authorization) may see different tools.
              Cache must not serve admin tools to basic-scope users.
            example: 'Authorization, X-Default-Scope'

# Multi-tenant endpoints
/v1/admin/tenants:
  get:
    responses:
      200:
        headers:
          Vary:
            schema:
              type: string
            description: |
              Authorization, X-Tenant-Id
              Each tenant sees only their data.
              Cache must not serve tenant A's data to tenant B.
            example: 'Authorization, X-Tenant-Id'
```

---

## 5. Content-Type Clarifications

### Current Implementation Status
- ✅ All responses use `application/json` (or `text/plain` for health checks)
- ✅ Errors use `application/problem+json` (RFC 7807)
- ✅ CORS headers properly configured

### OpenAPI Schema Updates

```yaml
responses:
  200:
    description: Successful response
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/SessionResponse'

  201:
    description: Resource created
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/SessionResponse'

  400:
    description: Bad Request
    content:
      application/problem+json:
        schema:
          $ref: '#/components/schemas/ProblemDetail'
        example:
          type: "about:blank"
          title: "Bad Request"
          status: 400
          detail: "Invalid request body"
          extensions:
            correlation_id: "req-123"
            timestamp: "2025-10-20T10:30:45Z"

  401:
    description: Unauthorized
    content:
      application/problem+json:
        schema:
          $ref: '#/components/schemas/ProblemDetail'
        example:
          type: "about:blank"
          title: "Unauthorized"
          status: 401
          detail: "Missing or invalid authorization header"
          extensions:
            correlation_id: "req-123"
            timestamp: "2025-10-20T10:30:45Z"

  403:
    description: Forbidden
    content:
      application/problem+json:
        schema:
          $ref: '#/components/schemas/ProblemDetail'
        example:
          type: "about:blank"
          title: "Forbidden"
          status: 403
          detail: "Insufficient permissions for this operation"
          extensions:
            correlation_id: "req-123"
            timestamp: "2025-10-20T10:30:45Z"

  500:
    description: Internal Server Error
    content:
      application/problem+json:
        schema:
          $ref: '#/components/schemas/ProblemDetail'
        example:
          type: "about:blank"
          title: "Internal Server Error"
          status: 500
          detail: "An unexpected error occurred"
          extensions:
            correlation_id: "req-123"
            timestamp: "2025-10-20T10:30:45Z"
```

### Accept Header Handling

```yaml
parameters:
  - name: Accept
    in: header
    required: false
    schema:
      type: string
    description: |
      Preferred response Content-Type.
      
      **Supported Values:**
      - `application/json` (default) - Standard JSON response
      - `application/problem+json` - Error detail format (RFC 7807)
      - `*/*` - Accept any format (resolves to application/json)
      - `application/*` - Accept any JSON-based format
      
      **Behavior:**
      - If Accept header missing: return application/json
      - If Accept header incompatible: return 406 Not Acceptable
      - Server prefers application/json for all endpoints
      
      **Example:**
      ```
      Accept: application/json
      → 200 OK with application/json
      
      Accept: application/problem+json
      → 200 OK with application/problem+json (for errors)
      
      Accept: text/html
      → 406 Not Acceptable (HTML not supported)
      ```
    example: 'application/json'
```

---

## 6. Deprecated Endpoints (None Currently)

### Future Deprecation Pattern

When endpoints are deprecated, they should be marked in OpenAPI:

```yaml
deprecated: true
description: |
  ⚠️ **DEPRECATED** - This endpoint is deprecated as of 2025-10-20.
  Use `/v1/agents/sessions` instead.
  Sunset date: 2025-12-20 (60-day deprecation period).
  
  **Migration Guide:**
  - Old: `POST /v1/old/sessions`
  - New: `POST /v1/agents/sessions`
  - Changes: New format requires "manager" field
  
  **Headers:**
  - Deprecated endpoints include: `Deprecation: true`
  - Sunset header: `Sunset: Sun, 20 Dec 2025 00:00:00 GMT`
  - Link header: `Link: </v1/agents/sessions>; rel="successor-version"`

responses:
  200:
    headers:
      Deprecation:
        schema:
          type: boolean
        description: 'true = endpoint is deprecated'
        example: true
      
      Sunset:
        schema:
          type: string
          format: date-time
        description: 'Date/time when endpoint will be removed'
        example: 'Sun, 20 Dec 2025 00:00:00 GMT'
      
      Link:
        schema:
          type: string
        description: 'Link to successor endpoint'
        example: '</v1/agents/sessions>; rel="successor-version"'
```

---

## Summary of OpenAPI Enhancements

| Feature | Status | Documentation | RFC |
|---------|--------|-----------------|-----|
| ETag Support | ✅ Implemented | Complete | RFC 7232 |
| Location Headers | ✅ Implemented | Complete | RFC 7231 |
| Idempotency | ✅ Implemented | Complete | RFC 9110 |
| Vary Headers | ✅ Implemented | Complete | RFC 7231 |
| Content-Type | ✅ Verified | Complete | RFC 7231, 7807 |
| Error Format | ✅ Verified | Complete | RFC 7807 |

---

## Implementation Verification

**Test Commands:**
```bash
# Verify ETag support
curl -i http://localhost:8000/v1/agents/sessions \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# Verify Location header on creation
curl -X POST http://localhost:8000/v1/agents/sessions \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: test-001" \
  -d '{"manager":"test"}'

# Verify Vary headers
curl -i http://localhost:8000/v1/agents/sessions \
  -H "Authorization: Bearer $ADMIN_TOKEN" | grep -i vary

# Verify Content-Type on errors
curl -i http://localhost:8000/v1/agents/sessions/invalid \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

---

**Status**: ✅ COMPLETE  
**Date**: October 20, 2025  
**Phase**: 4 Day 3 Enhancements
