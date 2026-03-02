# Phase 4 Day 3 - Content-Type Verification Guide

## Overview

This guide documents Content-Type verification for Phase 4 implementations:
- ✅ JSON responses on successful requests
- ✅ Problem+JSON on error responses (RFC 7807)
- ✅ Accept header negotiation
- ✅ CORS headers properly configured
- ✅ Response body validation

---

## 1. Content-Type Standards

### RFC 7231 - HTTP Semantics

The `Content-Type` header indicates the media type of the response body:

```
Content-Type: type/subtype [; parameters]
```

**Common Types**:
- `application/json` - JSON formatted data
- `application/problem+json` - Error details (RFC 7807)
- `text/plain` - Plain text
- `text/html` - HTML (not used here)

---

## 2. Response Content-Type Rules

### 2.1 Success Responses (2xx Status Codes)

#### GET Requests
```http
GET /v1/agents/sessions/123 HTTP/1.1
Authorization: Bearer $TOKEN

HTTP/1.1 200 OK
Content-Type: application/json; charset=utf-8
Vary: Authorization
ETag: "abc123"

{"session_id": "123", "status": "active", ...}
```

**Requirements**:
- ✅ Status Code: 200 OK
- ✅ Content-Type: `application/json`
- ✅ Charset: `utf-8` (recommended)
- ✅ Body: Valid JSON

**Verification Command**:
```bash
curl -i http://localhost:8000/v1/agents/sessions/123 \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  | grep -i "content-type"

# Expected output:
# Content-Type: application/json
```

#### POST Requests (201 Created)
```http
POST /v1/agents/sessions HTTP/1.1
Authorization: Bearer $TOKEN
Content-Type: application/json
Idempotency-Key: unique-id-001

{"manager": "test"}

HTTP/1.1 201 Created
Content-Type: application/json; charset=utf-8
Location: /v1/agents/sessions/f47ac10b-...
Idempotency-Key: unique-id-001
Idempotency-Replayed: false

{"session_id": "f47ac10b-...", "status": "active", ...}
```

**Requirements**:
- ✅ Status Code: 201 Created
- ✅ Content-Type: `application/json`
- ✅ Location header: Resource URL
- ✅ Body: Created resource JSON

#### 304 Not Modified
```http
GET /v1/agents/sessions/123 HTTP/1.1
Authorization: Bearer $TOKEN
If-None-Match: "abc123"

HTTP/1.1 304 Not Modified
ETag: "abc123"
(no body, no Content-Type header)
```

**Requirements**:
- ✅ Status Code: 304 Not Modified
- ✅ No body
- ✅ No Content-Type header
- ✅ ETag header present

---

## 3. Error Responses (4xx, 5xx Status Codes)

### 400 Bad Request
```http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json; charset=utf-8

{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "detail": "Invalid request body",
  "extensions": {
    "correlation_id": "req-12345",
    "timestamp": "2025-10-20T10:30:45Z"
  }
}
```

### 401 Unauthorized
```http
HTTP/1.1 401 Unauthorized
Content-Type: application/problem+json; charset=utf-8
WWW-Authenticate: Bearer realm="api"

{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Missing or invalid authorization header",
  "extensions": {
    "correlation_id": "req-12345",
    "timestamp": "2025-10-20T10:30:46Z"
  }
}
```

### 403 Forbidden
```http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json; charset=utf-8

{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "detail": "Insufficient permissions: requires admin:all scope",
  "extensions": {
    "required_scope": "admin:all",
    "user_scopes": ["tools:invoke:basic", "user:me"],
    "correlation_id": "req-12345",
    "timestamp": "2025-10-20T10:30:47Z"
  }
}
```

### 404 Not Found
```http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json; charset=utf-8

{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Session 'nonexistent-id' not found",
  "extensions": {
    "resource_type": "Session",
    "resource_id": "nonexistent-id",
    "correlation_id": "req-12345",
    "timestamp": "2025-10-20T10:30:48Z"
  }
}
```

### 500 Internal Server Error
```http
HTTP/1.1 500 Internal Server Error
Content-Type: application/problem+json; charset=utf-8

{
  "type": "about:blank",
  "title": "Internal Server Error",
  "status": 500,
  "detail": "An unexpected error occurred",
  "extensions": {
    "correlation_id": "req-12345",
    "timestamp": "2025-10-20T10:30:49Z"
  }
}
```

**All Error Responses**:
- ✅ Content-Type: `application/problem+json`
- ✅ RFC 7807 structure (type, title, status, detail, extensions)
- ✅ Correlation ID for tracing
- ✅ Timestamp for logging

---

## 4. Accept Header Negotiation

### Supported Values

| Accept Header | Response | Status |
|---------------|----------|--------|
| `application/json` | Content-Type: application/json | ✅ 200 OK |
| `application/*` | Content-Type: application/json | ✅ 200 OK |
| `*/*` | Content-Type: application/json | ✅ 200 OK |
| (missing) | Content-Type: application/json | ✅ 200 OK |
| `text/html` | 406 Not Acceptable | ❌ Unsupported |

### Accept Testing

```bash
# Accept application/json
curl http://localhost:8000/v1/agents/sessions/123 \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Accept: application/json"
# → 200 OK, application/json

# Accept */*
curl http://localhost:8000/v1/agents/sessions/123 \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Accept: */*"
# → 200 OK, application/json

# Accept unsupported type
curl http://localhost:8000/v1/agents/sessions/123 \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Accept: text/html"
# → 406 Not Acceptable
```

---

## 5. CORS Headers

### Required CORS Headers

```http
Access-Control-Allow-Origin: https://frontend.example.com
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET, POST, DELETE, OPTIONS
Access-Control-Allow-Headers: Authorization, Content-Type, Idempotency-Key
Access-Control-Expose-Headers: ETag, Location, Vary, Idempotency-Key, Idempotency-Replayed
Access-Control-Max-Age: 3600
```

### Critical: Exposed Headers

These headers MUST be in `Access-Control-Expose-Headers`:

| Header | Used For | Required |
|--------|----------|----------|
| ETag | Cache validation | ✅ Yes |
| Location | Resource discovery (201) | ✅ Yes |
| Vary | Cache variance | ✅ Yes |
| Idempotency-Key | Request echo | ✅ Yes |
| Idempotency-Replayed | Replay status | ✅ Yes |

**Verification**:
```bash
curl -i -X POST http://localhost:8000/v1/agents/sessions \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: cors-test" \
  -H "Origin: https://example.com" \
  -d '{"manager":"test"}' \
  | grep -i "access-control-expose-headers"

# Expected:
# Access-Control-Expose-Headers: ETag, Location, Vary, Idempotency-Key, Idempotency-Replayed
```

---

## 6. Verification Checklist

### Quick Verification Script

```bash
#!/bin/bash

echo "Phase 4 Content-Type Verification"
echo

# 1. Success response
echo "1. GET /sessions/{id} → 200 OK + application/json"
curl -s http://localhost:8000/v1/agents/sessions/test-123 \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -w "\nStatus: %{http_code}\nContent-Type: %{content_type}\n" \
  | tail -3

echo
echo "2. POST /sessions → 201 Created + Location header"
curl -s -X POST http://localhost:8000/v1/agents/sessions \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: verify-001" \
  -d '{"manager":"test"}' \
  -w "\nStatus: %{http_code}\nLocation: %{header{location}}\n" \
  | tail -3

echo
echo "3. 304 Not Modified (no body)"
ETAG=$(curl -s -D - http://localhost:8000/v1/agents/sessions/test-123 \
  -H "Authorization: Bearer $ADMIN_TOKEN" 2>/dev/null | grep -i "^etag:" | head -1 | sed 's/.*: //' | tr -d '\r')
curl -s -w "\nStatus: %{http_code}\nBody size: %{size_download}\n" \
  http://localhost:8000/v1/agents/sessions/test-123 \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "If-None-Match: $ETAG"

echo
echo "4. 401 Unauthorized → application/problem+json"
curl -s http://localhost:8000/v1/agents/sessions \
  -w "\nStatus: %{http_code}\nContent-Type: %{content_type}\n" \
  | tail -3

echo
echo "5. CORS Expose Headers"
curl -s -D - http://localhost:8000/v1/agents/sessions/test-123 \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Origin: https://example.com" 2>/dev/null \
  | grep -i "access-control-expose-headers"

echo
echo "Verification complete!"
```

---

## 7. Deployment Checklist

- [ ] All success responses (200, 201) use `application/json`
- [ ] All error responses (4xx, 5xx) use `application/problem+json`
- [ ] 304 responses have no Content-Type or body
- [ ] All responses include `charset=utf-8`
- [ ] Accept header negotiation returns 406 for unsupported types
- [ ] CORS headers include all required headers in Expose-Headers
- [ ] Problem details include type, title, status, detail, extensions
- [ ] Correlation IDs included in error responses
- [ ] Timestamps in ISO 8601 format

---

**Status**: ✅ COMPLETE  
**Date**: October 20, 2025  
**Phase**: 4 Day 3 Enhancements
