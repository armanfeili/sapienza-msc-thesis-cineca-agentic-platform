# Admin Processes Endpoint Descriptions

**Last Updated**: October 21, 2025  
**Status**: ✅ Complete - Human-readable descriptions applied

---

## Overview

This document contains the human-written, straightforward descriptions for all admin processes endpoints. These descriptions are now live in the FastAPI OpenAPI documentation at `/docs`.

---

## 1. GET /v1/admin/processes

**List active and recent built-in processes**

### Why we need this endpoint:
- Administrators need visibility into which AI models are currently running on the platform
- Essential for monitoring system resources and identifying stuck or stale processes
- Helps troubleshoot issues by seeing which models were recently active
- Without this, admins have no way to see what's happening on the system in real-time

### What it does:
- Shows all currently running built-in model processes (e.g., LLaMA, Whisper, embeddings)
- Displays recently stopped processes for audit purposes
- Merges live data from Redis with historical records from PostgreSQL
- Provides filtering by artifact name, status, tenant, and time range
- Returns process details including PID, port, status, and last heartbeat

### Access:
- Admin only – requires `admin:all` permission
- Returns 401 for missing/invalid tokens
- Returns 403 for non-admin users

### Behavior:
- **Data source**: Combines Redis runtime state + PostgreSQL audit logs
- **Sorting**: Active processes first, then by timestamp (newest first)
- **Pagination**: Default 100 results, max 1000 per request
- **Filters available**:
  - `artifact`: Model name (e.g., "llama3-8b")
  - `status`: Process status (running, starting, stopping, exited, stale)
  - `since`: ISO 8601 timestamp to see events after a specific time
  - `tenant_id`: Filter by tenant
  - `limit`: Number of results (1-1000)

### Responses:
- **200**: OK – Successfully retrieved process list with process details
- **401**: Unauthorized – Missing or invalid authentication token
- **403**: Forbidden – User lacks admin:all permission
- **500**: Internal Server Error – Database or Redis connection issue

### Examples:
```bash
# List all active processes
curl -X GET "http://localhost:8000/v1/admin/processes" \
     -H "Authorization: Bearer $ADMIN_TOKEN"

# Filter by artifact and status
curl -X GET "http://localhost:8000/v1/admin/processes?artifact=llama3-8b&status=running&limit=50" \
     -H "Authorization: Bearer $ADMIN_TOKEN"

# Get processes for specific tenant
curl -X GET "http://localhost:8000/v1/admin/processes?tenant_id=acme-corp" \
     -H "Authorization: Bearer $ADMIN_TOKEN"
```

---

## 2. DELETE /v1/admin/processes/{pid}

**Stop a built-in process by PID**

### Why we need this endpoint:
- Admins need ability to safely shut down misbehaving or stuck model processes
- Critical for resource management when a model is consuming too much memory or CPU
- Enables graceful cleanup before platform maintenance or restarts
- Without this, admins would have no way to stop runaway processes without killing the entire platform

### What it does:
- Gracefully stops a built-in model process using its operating system PID (process ID)
- Sends shutdown signal to the process via the runtime adapter
- Removes the process metadata from Redis cache
- Records a stop event in PostgreSQL for audit trail
- Works even if the process is already stopped or never existed (idempotent)

### Access:
- Admin only – requires `admin:all` permission
- Returns 401 for missing/invalid tokens
- Returns 403 for non-admin users

### Behavior:
- **Idempotency**: Multiple DELETE calls to the same PID always return 204
- **Concurrency safe**: Uses Redis stop-lock (30 second TTL) to prevent race conditions
- **Always succeeds**: Returns 204 whether process was stopped now, already stopped, or never existed
- **Graceful shutdown**: Attempts to unload process cleanly before terminating

### Responses:
- **204**: No Content – Process stopped successfully (or was already stopped/nonexistent)
- **401**: Unauthorized – Missing or invalid authentication token
- **403**: Forbidden – User lacks admin:all permission
- **422**: Unprocessable Entity – Invalid PID format (must be positive integer)
- **500**: Internal Server Error – Failed to communicate with Redis or database

### Examples:
```bash
# Stop a process by PID
curl -X DELETE "http://localhost:8000/v1/admin/processes/42789" \
     -H "Authorization: Bearer $ADMIN_TOKEN"

# Stop with correlation ID for tracking
curl -X DELETE "http://localhost:8000/v1/admin/processes/42789" \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "X-Correlation-Id: debug-12345"
```

---

## 3. GET /v1/admin/processes/history/manifests

**Get manifest activation history**

### Why we need this endpoint:
- Admins need to track when and how model configurations were deployed to the platform
- Essential for compliance and audit requirements to know who deployed what and when
- Helps troubleshoot issues by understanding which manifest versions are active or failed
- Without this, there's no way to know the deployment history or rollback to previous versions

### What it does:
- Shows the complete activation timeline of built-in manifest deployments
- Displays manifest name, version, activation time, and deployment status
- Tracks who activated each manifest (actor/user)
- Provides notes field for deployment context or troubleshooting information
- Enables filtering by manifest name, status, and time range

### Access:
- Admin only – requires `admin:all` permission
- Returns 401 for missing/invalid tokens
- Returns 403 for non-admin users

### Behavior:
- **Data source**: Queries PostgreSQL for persistent deployment records
- **Sorting**: Most recent activations first (newest to oldest)
- **Pagination**: Default 100 results, max 1000 per request
- **Filters available**:
  - `manifest_name`: Name of the manifest bundle
  - `status`: Deployment status (staged, active, rolled_back, failed)
  - `since`: ISO 8601 timestamp to see activations after a specific time
  - `limit`: Number of results (1-1000)

### Responses:
- **200**: OK – Successfully retrieved manifest history with deployment records
- **401**: Unauthorized – Missing or invalid authentication token
- **403**: Forbidden – User lacks admin:all permission
- **422**: Unprocessable Entity – Invalid status filter value
- **500**: Internal Server Error – Database query failed

### Examples:
```bash
# Get all manifest activations
curl -X GET "http://localhost:8000/v1/admin/processes/history/manifests" \
     -H "Authorization: Bearer $ADMIN_TOKEN"

# Filter by status and limit results
curl -X GET "http://localhost:8000/v1/admin/processes/history/manifests?status=active&limit=20" \
     -H "Authorization: Bearer $ADMIN_TOKEN"

# Get history for specific manifest
curl -X GET "http://localhost:8000/v1/admin/processes/history/manifests?manifest_name=llama-bundle" \
     -H "Authorization: Bearer $ADMIN_TOKEN"
```

---

## 4. GET /v1/admin/processes/history/processes

**Get process lifecycle event history**

### Why we need this endpoint:
- Admins need detailed forensic data to investigate process crashes, restarts, or performance issues
- Required for compliance to maintain complete audit logs of all process lifecycle events
- Essential for debugging by reconstructing exactly what happened to processes over time
- Without this, troubleshooting process issues would rely on scattered logs with no structured history

### What it does:
- Returns complete timeline of all process lifecycle events (start, heartbeat, stop, exit, signal)
- Shows full metadata for each event: PID, port, artifact, timestamp, exit codes, and reasons
- Tracks which tenant and manifest version each process belonged to
- Provides powerful filtering to narrow down specific processes or time periods
- Enables reconstruction of process behavior over time for root cause analysis

### Access:
- Admin only – requires `admin:all` permission
- Returns 401 for missing/invalid tokens
- Returns 403 for non-admin users

### Behavior:
- **Data source**: Queries PostgreSQL for persistent audit logs
- **Sorting**: Most recent events first (newest to oldest)
- **Pagination**: Default 100 results, max 1000 per request
- **Filters available**:
  - `artifact`: Model name (e.g., "llama3-8b")
  - `pid`: Operating system process ID
  - `process_id`: Stable internal process identifier
  - `tenant_id`: Filter by tenant
  - `event`: Event type (start, heartbeat, stop, exit, signal)
  - `since`: ISO 8601 timestamp to see events after a specific time
  - `limit`: Number of results (1-1000)

### Responses:
- **200**: OK – Successfully retrieved process event history with full event details
- **401**: Unauthorized – Missing or invalid authentication token
- **403**: Forbidden – User lacks admin:all permission
- **422**: Unprocessable Entity – Invalid event filter value
- **500**: Internal Server Error – Database query failed

### Examples:
```bash
# Get all process events
curl -X GET "http://localhost:8000/v1/admin/processes/history/processes" \
     -H "Authorization: Bearer $ADMIN_TOKEN"

# Filter by artifact and event type
curl -X GET "http://localhost:8000/v1/admin/processes/history/processes?artifact=whisper&event=start" \
     -H "Authorization: Bearer $ADMIN_TOKEN"

# Get events for specific PID
curl -X GET "http://localhost:8000/v1/admin/processes/history/processes?pid=42789" \
     -H "Authorization: Bearer $ADMIN_TOKEN"

# Filter by time range
curl -X GET "http://localhost:8000/v1/admin/processes/history/processes?since=2025-10-21T10:00:00Z&limit=100" \
     -H "Authorization: Bearer $ADMIN_TOKEN"
```

---

## Viewing the Documentation

All these descriptions are now live in the interactive API documentation:

1. **Swagger UI**: http://localhost:8000/docs
2. **ReDoc**: http://localhost:8000/redoc
3. **OpenAPI JSON**: http://localhost:8000/openapi.json

The descriptions follow a consistent structure:
- **Why we need this** - Business justification
- **What it does** - Functional description
- **Access** - Authentication and authorization
- **Behavior** - Technical details and features
- **Responses** - HTTP status codes with meanings
- **Examples** - Practical curl commands

---

## Implementation Notes

- All descriptions written in simple, straightforward language
- Avoiding technical jargon where possible
- Each endpoint explains the problem it solves
- Examples include real-world use cases
- Consistent formatting across all endpoints
- Focus on what matters to API consumers

**Status**: Ready for production ✅
