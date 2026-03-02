# Model Instances API Guide

Complete reference for model instance management endpoints with realistic examples for all major LLM providers.

---

## Table of Contents

- [Overview](#overview)
- [Core Concepts](#core-concepts)
- [Authentication & Headers](#authentication--headers)
- [POST /v1/admin/models/instances](#post-v1adminmodelsinstances)
- [GET /v1/admin/models/instances](#get-v1adminmodelsinstances)
- [GET /v1/admin/models/instances/{id}](#get-v1adminmodelsinstancesid)
- [DELETE /v1/admin/models/instances/{id}](#delete-v1adminmodelsinstancesid)
- [POST /v1/admin/models/instances/{id}/tests](#post-v1adminmodelsinstancesidtests)
- [PATCH /v1/admin/models/defaults](#patch-v1adminmodelsdefaults)
- [GET /v1/admin/models/defaults](#get-v1adminmodelsdefaults)
- [Provider-Specific Examples](#provider-specific-examples)
- [Error Handling](#error-handling)
- [Best Practices](#best-practices)

---

## Overview

The Model Instances API allows administrators to register, configure, and manage LLM model instances. Each instance represents a specific model (e.g., GPT-4o, Claude 3.5) hosted by a provider (OpenAI, Anthropic, Ollama, etc.).

**Key Features:**
- Multi-provider support (OpenAI, Azure OpenAI, OpenRouter, Ollama, custom providers)
- Tenant isolation (global or tenant-scoped instances)
- Idempotent operations (safe retry with Idempotency-Key)
- Default model selection (per-tenant or global)
- Real-time testing with observability

---

## Core Concepts

### Instance

A **model instance** represents a specific model configuration:

```typescript
{
  id: string;                    // UUID (auto-generated)
  instance_name: string;         // Human-readable name
  provider_id: string;           // Provider UUID (from /admin/models/providers)
  model_id: string;              // Provider's model identifier
  model_uri: string | null;      // Optional URI/path (Ollama, local models)
  tenant_id: string | null;      // Tenant scope (null = global)
  parameters: object;            // Model parameters (temperature, max_tokens, etc.)
  context_window: number | null; // Maximum context window
  modalities: string[];          // Supported modalities
  description: string | null;    // Human-friendly description
  enabled: boolean;              // Whether available for selection
  loaded: boolean;               // Whether runtime-loaded
}
```

### Provider

Before creating instances, register providers via:
```bash
POST /v1/admin/models/providers/register
```

See [Providers API documentation](./PROVIDERS_API_COMPLETE_SUMMARY.md) for details.

### Tenant Scoping

- **Global instances** (`tenant_id: null`): Available to all tenants
- **Tenant-scoped instances** (`tenant_id: "<uuid>"`): Visible only to specific tenant
- **Default resolution**: Tenant default > Global default > 404

---

## Authentication & Headers

### Required Headers

All endpoints require authentication:

```http
Authorization: Bearer <your_jwt_token>
```

**Permissions:**
- Read operations: Any authenticated user
- Write operations (POST, PATCH, DELETE): `admin:all` scope

### Optional Headers

#### Idempotency-Key

Safe retry protection for POST operations (24h replay window):

```http
Idempotency-Key: <unique-uuid>
```

**Behavior:**
- First request: `201 Created` with new instance
- Replay (same key): `200 OK` with existing instance
- Header: `Idempotency-Replayed: true`

#### X-Tenant-Id

Scope requests to specific tenant:

```http
X-Tenant-Id: <tenant-uuid-or-slug>
```

**Usage:**
- Filters list results to tenant + global instances
- Scopes default lookups to tenant-specific overrides

#### If-None-Match

Conditional requests for caching (all GET endpoints):

```http
If-None-Match: "abc123def456"
```

**Response:**
- `200 OK` with body if content changed
- `304 Not Modified` if ETag matches (no body)

### Standard Response Headers

All responses include:

```http
X-Request-Id: <correlation-id>
Cache-Control: no-cache, must-revalidate
Vary: Authorization
ETag: "<content-hash>"  # GET endpoints only
```

---

## POST /v1/admin/models/instances

**Create/register a new model instance.**

### Endpoint

```http
POST /v1/admin/models/instances
Content-Type: application/json
Authorization: Bearer <token>
Idempotency-Key: <optional-uuid>
X-Tenant-Id: <optional-tenant>
```

### Request Schema

```typescript
{
  provider_id: string;           // Required: Provider UUID
  instance_name: string;         // Required: Unique name
  model_id: string;              // Required: Model identifier
  model_uri?: string | null;     // Optional: Model URI/path
  tenant_id?: string | null;     // Optional: Tenant scope (null = global)
  parameters?: {                 // Optional: Model parameters
    temperature?: number;        // 0.0-2.0, default 0.7
    top_p?: number;              // 0.0-1.0, default 1.0
    max_tokens?: number;         // 1-provider_max, default varies
    stop?: string[];             // Stop sequences
    frequency_penalty?: number;  // -2.0-2.0, default 0.0
    presence_penalty?: number;   // -2.0-2.0, default 0.0
    response_format?: string;    // "text" | "json_object"
    seed?: number;               // Reproducibility seed
  };
  context_window?: number | null; // Min: 1024, max: provider-specific
  modalities?: string[];          // ["text", "vision", "audio", "tool"]
  description?: string | null;    // Human-friendly description
}
```

### Schema Constraints

#### `modalities`

**Enum:** `["text", "vision", "audio", "tool"]`

```json
{
  "modalities": ["text", "vision"]  // GPT-4o, Claude 3.5 Sonnet
}
```

#### `context_window`

**Constraints:** Min: 1024, nullable

```json
{
  "context_window": 128000  // GPT-4o, GPT-4-Turbo
}
```

#### `parameters`

Known fields with `additionalProperties: true`:

```typescript
{
  // Standard OpenAI-compatible fields
  temperature: number;          // Randomness (0.0 = deterministic)
  top_p: number;                // Nucleus sampling
  max_tokens: number;           // Output limit
  stop: string[];               // Stop sequences
  frequency_penalty: number;    // Penalize repetition
  presence_penalty: number;     // Penalize presence
  response_format: string;      // "text" | "json_object"
  seed: number;                 // Reproducibility
  
  // Provider-specific (additionalProperties)
  num_ctx?: number;             // Ollama context window
  num_predict?: number;         // Ollama max output
  repeat_penalty?: number;      // Ollama repetition penalty
  azure_deployment?: string;    // Azure OpenAI deployment name
}
```

#### `provider_id` Format

**Type:** UUID string

```json
{
  "provider_id": "8fcc3c98-aa43-4977-98ea-1394e32b6530"  // UUID format
}
```

**Resolution:** Validates against `GET /v1/admin/models/providers`

**Note:** Current data shows slugs (e.g., "ollama-local") in some legacy responses. API should standardize on UUIDs. Deprecate slug support in future release.

#### `tenant_id` Semantics

**Type:** UUID string | null

```json
{
  "tenant_id": null  // Global instance (available to all tenants)
}
```

```json
{
  "tenant_id": "tenant-123-uuid"  // Tenant-scoped instance
}
```

**Null semantics:** Global instance, visible to all tenants

### Response

#### Success (201 Created)

```json
{
  "id": "8fcc3c98-aa43-4977-98ea-1394e32b6530",
  "instance_name": "gpt-4o",
  "provider_id": "provider-uuid",
  "model_id": "gpt-4o",
  "enabled": true,
  "loaded": true,
  "created_at": "2025-10-17T12:34:56Z",
  "etag": "abc123def456"
}
```

**Headers:**
```http
HTTP/1.1 201 Created
Location: /v1/admin/models/instances/8fcc3c98-aa43-4977-98ea-1394e32b6530
X-Request-Id: trace-a1b2c3d4
Idempotency-Key: <echoed>
Idempotency-Replayed: false
```

#### Idempotent Replay (200 OK)

```json
{
  "id": "8fcc3c98-aa43-4977-98ea-1394e32b6530",
  "instance_name": "gpt-4o",
  "provider_id": "provider-uuid",
  "model_id": "gpt-4o",
  "enabled": true,
  "loaded": true,
  "created_at": "2025-10-17T12:34:56Z",
  "etag": "abc123def456"
}
```

**Headers:**
```http
HTTP/1.1 200 OK
X-Request-Id: trace-a1b2c3d4
Idempotency-Key: <echoed>
Idempotency-Replayed: true
```

#### Error (400 Bad Request)

```json
{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "detail": "Provider not found: provider-uuid",
  "instance": "/v1/admin/models/instances"
}
```

### Examples by Provider

#### OpenAI – GPT-4o (text+vision)

**Request:**
```bash
curl -X POST "$BASE_URL/v1/admin/models/instances" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{
    "provider_id": "openai-provider-uuid",
    "instance_name": "gpt-4o",
    "model_id": "gpt-4o",
    "model_uri": null,
    "tenant_id": null,
    "parameters": {
      "temperature": 0.2,
      "top_p": 1.0,
      "max_tokens": 2048,
      "presence_penalty": 0.0,
      "frequency_penalty": 0.0,
      "stop": ["```", "\n\n"],
      "response_format": "text"
    },
    "context_window": 128000,
    "modalities": ["text", "vision"],
    "description": "OpenAI GPT-4o (128k context) for general chat + vision"
  }'
```

**Response:**
```json
{
  "id": "inst-uuid-1",
  "instance_name": "gpt-4o",
  "provider_id": "openai-provider-uuid",
  "model_id": "gpt-4o",
  "enabled": true,
  "loaded": true,
  "created_at": "2025-10-17T12:00:00Z",
  "etag": "abc123"
}
```

#### OpenAI – GPT-4o-mini (cheap, fast)

```json
{
  "provider_id": "openai-provider-uuid",
  "instance_name": "gpt-4o-mini",
  "model_id": "gpt-4o-mini",
  "model_uri": null,
  "tenant_id": null,
  "parameters": {
    "temperature": 0.3,
    "top_p": 1.0,
    "max_tokens": 1024,
    "stop": ["\n\n"]
  },
  "context_window": 128000,
  "modalities": ["text", "vision"],
  "description": "OpenAI GPT-4o-mini for low-latency tasks"
}
```

#### Legacy OpenAI – GPT-3.5-Turbo

```json
{
  "provider_id": "openai-provider-uuid",
  "instance_name": "gpt-3.5-turbo-0125",
  "model_id": "gpt-3.5-turbo-0125",
  "model_uri": null,
  "tenant_id": null,
  "parameters": {
    "temperature": 0.3,
    "top_p": 1.0,
    "max_tokens": 512,
    "stop": ["\n\n"]
  },
  "context_window": 16385,
  "modalities": ["text"],
  "description": "Legacy GPT-3.5 Turbo (kept for backward compatibility)"
}
```

#### Azure OpenAI – GPT-4o via deployment

```json
{
  "provider_id": "azure-openai-provider-uuid",
  "instance_name": "gpt-4o-azure",
  "model_id": "gpt-4o",
  "model_uri": "azure-openai://my-azure-resource/my-gpt4o-deployment?api-version=2024-02-15-preview",
  "tenant_id": null,
  "parameters": {
    "temperature": 0.2,
    "top_p": 1.0,
    "max_tokens": 2048,
    "stop": ["```", "---"],
    "azure_deployment": "my-gpt4o-deployment"
  },
  "context_window": 128000,
  "modalities": ["text", "vision"],
  "description": "Azure OpenAI GPT-4o (deployment-bound)"
}
```

#### OpenRouter – GPT-4o proxy

```json
{
  "provider_id": "openrouter-provider-uuid",
  "instance_name": "gpt-4o-openrouter",
  "model_id": "openai/gpt-4o",
  "model_uri": "openrouter://openai/gpt-4o",
  "tenant_id": null,
  "parameters": {
    "temperature": 0.2,
    "top_p": 1.0,
    "max_tokens": 2048
  },
  "context_window": 128000,
  "modalities": ["text", "vision"],
  "description": "GPT-4o via OpenRouter"
}
```

#### Ollama – Llama 3.2 (3B instruct)

```json
{
  "provider_id": "ollama-local-provider-uuid",
  "instance_name": "llama3.2-3b-instruct",
  "model_id": "llama3.2:3b-instruct",
  "model_uri": null,
  "tenant_id": null,
  "parameters": {
    "temperature": 0.0,
    "num_ctx": 8192,
    "num_predict": 512,
    "repeat_penalty": 1.1,
    "stop": ["\n\n", "```"]
  },
  "context_window": 8192,
  "modalities": ["text"],
  "description": "Llama 3.2 3B Instruct (local, fast inference)"
}
```

---

## GET /v1/admin/models/instances

**List all registered model instances.**

### Endpoint

```http
GET /v1/admin/models/instances
Authorization: Bearer <token>
If-None-Match: "<etag>"
X-Tenant-Id: <optional-tenant>
```

### Query Parameters

```typescript
{
  tenant_id?: string;    // Filter by tenant UUID (null for global)
  provider_id?: string;  // Filter by provider UUID
  loaded?: boolean;      // Filter by loaded status
  enabled?: boolean;     // Filter by enabled status
  page_size?: number;    // Items per page (1-1000, default 100)
  page_token?: string;   // Continuation token from previous response
}
```

### Response

#### Success (200 OK)

```json
{
  "items": [
    {
      "id": "inst-uuid-1",
      "instance_name": "gpt-4o",
      "provider_id": "provider-uuid",
      "model_id": "gpt-4o",
      "model_uri": null,
      "tenant_id": null,
      "parameters": { "temperature": 0.2, "max_tokens": 2048 },
      "context_window": 128000,
      "modalities": ["text", "vision"],
      "description": "OpenAI GPT-4o (128k)",
      "enabled": true,
      "loaded": true,
      "created_at": "2025-10-17T12:00:00Z",
      "updated_at": "2025-10-17T12:00:00Z"
    }
  ],
  "total": 1,
  "etag": "abc123def456",
  "next_page_token": null
}
```

**Headers:**
```http
HTTP/1.1 200 OK
ETag: "abc123def456"
Cache-Control: no-cache, must-revalidate
Vary: Authorization
X-Request-Id: trace-a1b2c3d4
```

#### Cache Hit (304 Not Modified)

```http
HTTP/1.1 304 Not Modified
ETag: "abc123def456"
Cache-Control: no-cache, must-revalidate
Vary: Authorization
X-Request-Id: trace-a1b2c3d4
```

### Examples

#### List all instances

```bash
curl -X GET "$BASE_URL/v1/admin/models/instances" \
  -H "Authorization: Bearer $TOKEN"
```

#### List tenant-scoped instances

```bash
curl -X GET "$BASE_URL/v1/admin/models/instances?tenant_id=tenant-uuid" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-Id: tenant-uuid"
```

#### List instances from specific provider

```bash
curl -X GET "$BASE_URL/v1/admin/models/instances?provider_id=provider-uuid" \
  -H "Authorization: Bearer $TOKEN"
```

#### List only loaded instances

```bash
curl -X GET "$BASE_URL/v1/admin/models/instances?loaded=true" \
  -H "Authorization: Bearer $TOKEN"
```

#### Pagination

```bash
# First page
curl -X GET "$BASE_URL/v1/admin/models/instances?page_size=50" \
  -H "Authorization: Bearer $TOKEN"

# Next page (use next_page_token from response)
curl -X GET "$BASE_URL/v1/admin/models/instances?page_size=50&page_token=next-token" \
  -H "Authorization: Bearer $TOKEN"
```

#### Conditional request (caching)

```bash
# First request: Get ETag
curl -i -X GET "$BASE_URL/v1/admin/models/instances" \
  -H "Authorization: Bearer $TOKEN"
# → Response includes: ETag: "abc123def456"

# Subsequent requests: Send If-None-Match
curl -i -X GET "$BASE_URL/v1/admin/models/instances" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'If-None-Match: "abc123def456"'
# → If unchanged: 304 Not Modified (no body)
# → If changed: 200 OK with new body and ETag
```

---

## GET /v1/admin/models/instances/{id}

**Get details for a specific model instance.**

### Endpoint

```http
GET /v1/admin/models/instances/{instance_id}
Authorization: Bearer <token>
If-None-Match: "<etag>"
```

### Response

#### Success (200 OK)

```json
{
  "id": "inst-uuid-1",
  "instance_name": "gpt-4o",
  "provider_id": "provider-uuid",
  "model_id": "gpt-4o",
  "model_uri": null,
  "tenant_id": null,
  "parameters": {
    "temperature": 0.2,
    "top_p": 1.0,
    "max_tokens": 2048,
    "stop": ["```", "\n\n"]
  },
  "context_window": 128000,
  "modalities": ["text", "vision"],
  "description": "OpenAI GPT-4o (128k context)",
  "enabled": true,
  "loaded": true,
  "created_at": "2025-10-17T12:00:00Z",
  "updated_at": "2025-10-17T12:00:00Z",
  "etag": "abc123def456"
}
```

**Headers:**
```http
HTTP/1.1 200 OK
ETag: "abc123def456"
Cache-Control: no-cache, must-revalidate
Vary: Authorization
X-Request-Id: trace-a1b2c3d4
```

#### Not Found (404)

```json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Instance not found: inst-uuid-1",
  "instance": "/v1/admin/models/instances/inst-uuid-1"
}
```

### Examples

```bash
curl -X GET "$BASE_URL/v1/admin/models/instances/inst-uuid-1" \
  -H "Authorization: Bearer $TOKEN"
```

---

## DELETE /v1/admin/models/instances/{id}

**Delete (unload) a model instance.**

### Endpoint

```http
DELETE /v1/admin/models/instances/{instance_id}
Authorization: Bearer <token>
```

### Behavior

- Acquires exclusive lock (15s TTL) to prevent concurrent operations
- Marks instance as unloaded or fully removes it
- Invalidates all related caches
- Auto-clears any defaults pointing to this instance

### Response

#### Success (204 No Content)

```http
HTTP/1.1 204 No Content
X-Request-Id: trace-a1b2c3d4
X-Event-Id: event-a1b2c3d4
X-Trace-Id: trace-a1b2c3d4
```

#### Conflict (409)

```json
{
  "type": "about:blank",
  "title": "Conflict",
  "status": 409,
  "detail": "Instance operation already in progress (lock held)",
  "instance": "/v1/admin/models/instances/inst-uuid-1"
}
```

#### Not Found (404)

```json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Instance not found: inst-uuid-1",
  "instance": "/v1/admin/models/instances/inst-uuid-1"
}
```

### Examples

```bash
curl -X DELETE "$BASE_URL/v1/admin/models/instances/inst-uuid-1" \
  -H "Authorization: Bearer $TOKEN"
```

---

## POST /v1/admin/models/instances/{id}/tests

**Test a model instance with a prompt.**

### Endpoint

```http
POST /v1/admin/models/instances/{instance_id}/tests
Content-Type: application/json
Authorization: Bearer <token>
```

### Request Schema

```typescript
{
  prompt?: string;               // Test prompt (converted to user message)
  messages?: Array<{             // Pre-formatted chat messages (alternative)
    role: "system" | "user" | "assistant";
    content: string;
  }>;
  temperature?: number;          // 0.0-2.0, default 0.0
  max_tokens?: number;           // 1-8000, default 32
  stop?: string[];               // Stop sequences (null = smart defaults)
  one_sentence?: boolean;        // Enforce single-sentence (default true)
  no_system?: boolean;           // Skip system message injection (default false)
  format_hint?: string;          // "poem", "list", "json", etc.
}
```

### Response Schema

```typescript
{
  model: string;                 // Model used
  output: string;                // Generated text
  usage: {                       // Token usage
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  } | null;
  trace_id: string;              // Provenance trace ID
  event_id: string;              // Provenance event ID
  provider: string | null;       // Provider used
  provider_base_url: string | null; // Provider URL (debugging)
  latency_ms: number | null;     // Request latency
  parameters: {                  // Actual parameters used
    temperature: number;
    max_tokens: number;
    stop: string[];
    one_sentence: boolean;
    format_hint?: string;
  };
}
```

### Examples

#### Factual query (deterministic)

**Request:**
```bash
curl -X POST "$BASE_URL/v1/admin/models/instances/inst-uuid-1/tests" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Explain quantum computing in one sentence.",
    "temperature": 0.0,
    "max_tokens": 64
  }'
```

**Response:**
```json
{
  "model": "gpt-4o",
  "output": "Quantum computing uses quantum-mechanical phenomena such as superposition and entanglement to perform calculations exponentially faster than classical computers for certain problems.",
  "usage": {
    "prompt_tokens": 15,
    "completion_tokens": 28,
    "total_tokens": 43
  },
  "trace_id": "trace-a1b2c3d4",
  "event_id": "event-a1b2c3d4",
  "provider": "openai-provider-uuid",
  "provider_base_url": "https://api.openai.com/v1",
  "latency_ms": 1842.5,
  "parameters": {
    "temperature": 0.0,
    "max_tokens": 64,
    "stop": ["\n"],
    "one_sentence": true
  }
}
```

#### Short answer with custom stop

**Request:**
```bash
curl -X POST "$BASE_URL/v1/admin/models/instances/inst-uuid-1/tests" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "What is the capital of France?",
    "temperature": 0.0,
    "max_tokens": 32,
    "stop": ["\n\n"]
  }'
```

**Response:**
```json
{
  "model": "gpt-4o",
  "output": "Paris.",
  "usage": {
    "prompt_tokens": 8,
    "completion_tokens": 2,
    "total_tokens": 10
  },
  "trace_id": "trace-b2c3d4e5",
  "event_id": "event-b2c3d4e5",
  "provider": "openai-provider-uuid",
  "provider_base_url": "https://api.openai.com/v1",
  "latency_ms": 423.1,
  "parameters": {
    "temperature": 0.0,
    "max_tokens": 32,
    "stop": ["\n\n"],
    "one_sentence": true
  }
}
```

#### Creative task (non-deterministic)

**Request:**
```bash
curl -X POST "$BASE_URL/v1/admin/models/instances/inst-uuid-1/tests" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Write a haiku about programming.",
    "temperature": 0.7,
    "max_tokens": 100,
    "one_sentence": false,
    "format_hint": "poem"
  }'
```

**Response:**
```json
{
  "model": "gpt-4o",
  "output": "Code flows like water,\nBugs hide in silent shadows,\nDebug until dawn.",
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 22,
    "total_tokens": 32
  },
  "trace_id": "trace-c3d4e5f6",
  "event_id": "event-c3d4e5f6",
  "provider": "openai-provider-uuid",
  "provider_base_url": "https://api.openai.com/v1",
  "latency_ms": 1127.8,
  "parameters": {
    "temperature": 0.7,
    "max_tokens": 100,
    "stop": ["\n\n", "```", "---"],
    "one_sentence": false,
    "format_hint": "poem"
  }
}
```

#### Pre-formatted messages

**Request:**
```bash
curl -X POST "$BASE_URL/v1/admin/models/instances/inst-uuid-1/tests" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "system", "content": "You are a helpful assistant that responds in JSON."},
      {"role": "user", "content": "What is 2+2?"}
    ],
    "temperature": 0.0,
    "max_tokens": 64
  }'
```

---

## PATCH /v1/admin/models/defaults

**Set the default model.**

### Endpoint

```http
PATCH /v1/admin/models/defaults
Content-Type: application/json
Authorization: Bearer <token>
X-Tenant-Id: <optional-tenant>
```

### Request Schema (Preferred)

```json
{
  "chat": {
    "instance_id": "<uuid>"
  }
}
```

### Request Schema (Alternative - Legacy)

```json
{
  "chat": {
    "name": "<instance-name>"
  }
}
```

```json
{
  "name": "<instance-name>"
}
```

**Note:** The preferred format uses `instance_id` for unambiguous resolution. The `name` format is retained for backward compatibility but may be deprecated in future releases.

### Tenant Defaults Support

**Precedence:**
1. Tenant-scoped default (if `X-Tenant-Id` provided and tenant has default)
2. Global default (if no tenant default)
3. 404 (if no defaults configured)

**Set tenant-specific default:**
```bash
curl -X PATCH "$BASE_URL/v1/admin/models/defaults" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-Id: tenant-uuid" \
  -H "Content-Type: application/json" \
  -d '{"chat": {"instance_id": "inst-uuid-1"}}'
```

**Set global default:**
```bash
curl -X PATCH "$BASE_URL/v1/admin/models/defaults" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"chat": {"instance_id": "inst-uuid-1"}}'
```

### Response

#### Success (200 OK)

```json
{
  "ok": true,
  "message": "Default model updated successfully",
  "instance_id": "inst-uuid-1",
  "instance_name": "gpt-4o"
}
```

**Headers:**
```http
HTTP/1.1 200 OK
X-Request-Id: trace-a1b2c3d4
ETag: "abc123def456"
Cache-Control: no-cache, must-revalidate
```

**Note:** Updating defaults invalidates the cache. Response includes new ETag for subsequent conditional requests.

#### Not Found (404)

```json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Instance not found: inst-uuid-1",
  "instance": "/v1/admin/models/defaults"
}
```

### Examples

#### Preferred: Set by instance_id

```bash
curl -X PATCH "$BASE_URL/v1/admin/models/defaults" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "chat": {
      "instance_id": "8fcc3c98-aa43-4977-98ea-1394e32b6530"
    }
  }'
```

#### Alternative: Set by name (legacy)

```bash
curl -X PATCH "$BASE_URL/v1/admin/models/defaults" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "chat": {
      "name": "gpt-4o"
    }
  }'
```

#### Strict legacy (deprecated)

```bash
curl -X PATCH "$BASE_URL/v1/admin/models/defaults" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "gpt-4o"
  }'
```

---

## GET /v1/admin/models/defaults

**Get the current default model.**

### Endpoint

```http
GET /v1/admin/models/defaults
Authorization: Bearer <token>
If-None-Match: "<etag>"
X-Tenant-Id: <optional-tenant>
```

### Response

#### Success (200 OK)

```json
{
  "chat": {
    "instance_id": "inst-uuid-1",
    "name": "gpt-4o",
    "provider_id": "provider-uuid",
    "model_id": "gpt-4o"
  },
  "etag": "abc123def456"
}
```

**Headers:**
```http
HTTP/1.1 200 OK
ETag: "abc123def456"
Cache-Control: no-cache, must-revalidate
Vary: Authorization
X-Request-Id: trace-a1b2c3d4
```

#### Not Found (404)

**Current behavior:**
```json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "No default model configured",
  "instance": "/v1/admin/models/defaults"
}
```

**Proposed alternative (unset shape):**
```json
{
  "chat": null,
  "etag": "abc123def456"
}
```

**Status:** 200 OK

**Rationale:** Makes it easier for clients to distinguish "no default set" from "endpoint/resource doesn't exist". Current behavior (404) is acceptable but less ergonomic.

### Examples

#### Get global default

```bash
curl -X GET "$BASE_URL/v1/admin/models/defaults" \
  -H "Authorization: Bearer $TOKEN"
```

#### Get tenant-specific default

```bash
curl -X GET "$BASE_URL/v1/admin/models/defaults" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-Id: tenant-uuid"
```

#### Conditional request (caching)

```bash
# First request
curl -i -X GET "$BASE_URL/v1/admin/models/defaults" \
  -H "Authorization: Bearer $TOKEN"
# → Response includes: ETag: "abc123def456"

# Subsequent requests
curl -i -X GET "$BASE_URL/v1/admin/models/defaults" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'If-None-Match: "abc123def456"'
# → If unchanged: 304 Not Modified
# → If changed: 200 OK with new body
```

---

## Provider-Specific Examples

### Complete OpenAI Setup

```bash
# 1. Register OpenAI provider
curl -X POST "$BASE_URL/v1/admin/models/providers/register" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "openai",
    "type": "openai_compatible",
    "base_url": "https://api.openai.com/v1",
    "api_key": "sk-...",
    "model": null,
    "tenant_id": null,
    "config": null
  }'
# → Response: {"ok": true, "message": "Successfully registered provider openai", "details": {...}}
# Note the provider UUID from response

# 2. Create GPT-4o instance
curl -X POST "$BASE_URL/v1/admin/models/instances" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{
    "provider_id": "<provider-uuid-from-step-1>",
    "instance_name": "gpt-4o",
    "model_id": "gpt-4o",
    "model_uri": null,
    "tenant_id": null,
    "parameters": {
      "temperature": 0.2,
      "top_p": 1.0,
      "max_tokens": 2048,
      "stop": ["```", "\n\n"]
    },
    "context_window": 128000,
    "modalities": ["text", "vision"],
    "description": "OpenAI GPT-4o (128k context)"
  }'
# → Response: {"id": "inst-uuid", ...}

# 3. Set as default
curl -X PATCH "$BASE_URL/v1/admin/models/defaults" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "chat": {
      "instance_id": "<inst-uuid-from-step-2>"
    }
  }'

# 4. Test instance
curl -X POST "$BASE_URL/v1/admin/models/instances/<inst-uuid>/tests" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Explain quantum computing in one sentence.",
    "temperature": 0.0,
    "max_tokens": 64
  }'
```

### Complete Azure OpenAI Setup

```bash
# 1. Register Azure OpenAI provider
curl -X POST "$BASE_URL/v1/admin/models/providers/register" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "azure-openai",
    "type": "openai_compatible",
    "base_url": "https://my-resource.openai.azure.com",
    "api_key": "...",
    "model": null,
    "tenant_id": null,
    "config": {
      "api_version": "2024-02-15-preview",
      "paths": {
        "chat_completions": "/openai/deployments/my-gpt4o-deployment/chat/completions"
      }
    }
  }'

# 2. Create GPT-4o instance (deployment-bound)
curl -X POST "$BASE_URL/v1/admin/models/instances" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{
    "provider_id": "<azure-provider-uuid>",
    "instance_name": "gpt-4o-azure",
    "model_id": "gpt-4o",
    "model_uri": "azure-openai://my-resource/my-gpt4o-deployment?api-version=2024-02-15-preview",
    "tenant_id": null,
    "parameters": {
      "temperature": 0.2,
      "max_tokens": 2048,
      "azure_deployment": "my-gpt4o-deployment"
    },
    "context_window": 128000,
    "modalities": ["text", "vision"],
    "description": "Azure OpenAI GPT-4o (deployment-bound)"
  }'

# 3. Test
curl -X POST "$BASE_URL/v1/admin/models/instances/<inst-uuid>/tests" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "What is the capital of France?",
    "temperature": 0.0,
    "max_tokens": 32
  }'
```

### Complete Ollama Setup

```bash
# 1. Register Ollama provider (local)
curl -X POST "$BASE_URL/v1/admin/models/providers/register" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "ollama-local",
    "type": "openai_compatible",
    "base_url": "http://host.docker.internal:11434/v1",
    "api_key": null,
    "model": null,
    "tenant_id": null,
    "config": {
      "paths": {
        "chat_completions": "/chat/completions"
      }
    }
  }'

# 2. Create Llama 3.2 3B instance
curl -X POST "$BASE_URL/v1/admin/models/instances" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{
    "provider_id": "<ollama-provider-uuid>",
    "instance_name": "llama3.2-3b-instruct",
    "model_id": "llama3.2:3b-instruct",
    "model_uri": null,
    "tenant_id": null,
    "parameters": {
      "temperature": 0.0,
      "num_ctx": 8192,
      "num_predict": 512,
      "repeat_penalty": 1.1
    },
    "context_window": 8192,
    "modalities": ["text"],
    "description": "Llama 3.2 3B Instruct (local)"
  }'

# 3. Test (note: first run may auto-pull model)
curl -X POST "$BASE_URL/v1/admin/models/instances/<inst-uuid>/tests" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Explain quantum computing in one sentence.",
    "temperature": 0.0,
    "max_tokens": 64
  }'
```

### Complete OpenRouter Setup

```bash
# 1. Register OpenRouter provider
curl -X POST "$BASE_URL/v1/admin/models/providers/register" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "openrouter",
    "type": "openai_compatible",
    "base_url": "https://openrouter.ai/api/v1",
    "api_key": "sk-or-v1-...",
    "model": null,
    "tenant_id": null,
    "config": {
      "headers": {
        "HTTP-Referer": "https://your-app.com",
        "X-Title": "Your App Name"
      }
    }
  }'

# 2. Create GPT-4o instance (via OpenRouter)
curl -X POST "$BASE_URL/v1/admin/models/instances" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{
    "provider_id": "<openrouter-provider-uuid>",
    "instance_name": "gpt-4o-openrouter",
    "model_id": "openai/gpt-4o",
    "model_uri": "openrouter://openai/gpt-4o",
    "tenant_id": null,
    "parameters": {
      "temperature": 0.2,
      "max_tokens": 2048
    },
    "context_window": 128000,
    "modalities": ["text", "vision"],
    "description": "GPT-4o via OpenRouter"
  }'

# 3. Test
curl -X POST "$BASE_URL/v1/admin/models/instances/<inst-uuid>/tests" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "What is the capital of France?",
    "temperature": 0.0,
    "max_tokens": 32
  }'
```

---

## Error Handling

### Unified Error Schema (RFC 7807)

All errors follow the Problem Details specification:

```json
{
  "type": "about:blank",
  "title": "<HTTP status reason>",
  "status": <HTTP status code>,
  "detail": "<human-readable error message>",
  "instance": "<request path>",
  "extensions": {
    "correlation_id": "<trace-id>",
    "event_id": "<event-id>"
  }
}
```

### Common Error Codes

#### 400 Bad Request

**Causes:**
- Missing required fields
- Invalid field values
- Business logic violations

**Example:**
```json
{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "detail": "Provider not found: provider-uuid",
  "instance": "/v1/admin/models/instances"
}
```

#### 401 Unauthorized

**Causes:**
- Missing `Authorization` header
- Invalid token
- Expired token

**Example:**
```json
{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Not authenticated"
}
```

#### 403 Forbidden

**Causes:**
- Insufficient permissions (missing `admin:all`)
- Egress allowlist violation

**Example:**
```json
{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "detail": "Admin scope required"
}
```

#### 404 Not Found

**Causes:**
- Instance doesn't exist
- Default not configured
- Resource not found

**Example:**
```json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Instance not found: inst-uuid-1",
  "instance": "/v1/admin/models/instances/inst-uuid-1"
}
```

#### 409 Conflict

**Causes:**
- Instance already exists (duplicate name)
- Instance operation in progress (lock held)
- Concurrent modification

**Example:**
```json
{
  "type": "about:blank",
  "title": "Conflict",
  "status": 409,
  "detail": "Instance operation already in progress (lock held)",
  "instance": "/v1/admin/models/instances/inst-uuid-1"
}
```

#### 422 Validation Error

**Causes:**
- Invalid request body structure
- Type mismatches
- Schema validation failures

**Example:**
```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "provider_id"],
      "msg": "Field required",
      "input": {"instance_name": "test"}
    }
  ]
}
```

#### 502 Bad Gateway

**Causes:**
- Provider unreachable
- Provider returned error
- Network timeout

**Example:**
```json
{
  "type": "about:blank",
  "title": "Bad Gateway",
  "status": 502,
  "detail": "Provider returned 404: model not found",
  "provider": "openai-provider-uuid",
  "provider_base_url": "https://api.openai.com/v1",
  "model": "gpt-4o"
}
```

#### 504 Gateway Timeout

**Causes:**
- Provider timeout (>60s)
- Connection refused
- DNS resolution failure

**Example:**
```json
{
  "type": "about:blank",
  "title": "Gateway Timeout",
  "status": 504,
  "detail": "Provider connection failed: ConnectError",
  "provider": "ollama-local-provider-uuid",
  "provider_base_url": "http://host.docker.internal:11434/v1",
  "model": "llama3.2:3b-instruct",
  "timeout_seconds": 60.0,
  "warmed": false,
  "retried": true,
  "latency_ms": 60123.4
}
```

---

## Best Practices

### 1. Use Idempotency-Key for POST Operations

Always include `Idempotency-Key` for safe retries:

```bash
curl -X POST "$BASE_URL/v1/admin/models/instances" \
  -H "Idempotency-Key: $(uuidgen)" \
  -H "..." \
  -d '{...}'
```

**Benefits:**
- Safe retry on network failures
- Prevents duplicate instances
- 24h replay window

### 2. Leverage ETag for Caching

Use `If-None-Match` for conditional GETs:

```bash
# First request
ETAG=$(curl -sI "$BASE_URL/v1/admin/models/instances" \
  -H "Authorization: Bearer $TOKEN" \
  | grep -i "etag" | cut -d' ' -f2 | tr -d '\r')

# Subsequent requests
curl -X GET "$BASE_URL/v1/admin/models/instances" \
  -H "Authorization: Bearer $TOKEN" \
  -H "If-None-Match: $ETAG"
```

**Benefits:**
- Reduces bandwidth
- Lower server load
- Faster responses (304 = no body)

### 3. Use UUID for provider_id

Always use UUID format, not slugs:

```json
{
  "provider_id": "8fcc3c98-aa43-4977-98ea-1394e32b6530"  // ✅ UUID
}
```

```json
{
  "provider_id": "openai"  // ❌ Slug (deprecated)
}
```

### 4. Set Sensible Defaults for Parameters

Use provider-appropriate defaults:

**OpenAI models:**
```json
{
  "parameters": {
    "temperature": 0.2,      // Slightly creative
    "top_p": 1.0,            // Full probability mass
    "max_tokens": 2048,      // Reasonable limit
    "stop": ["```", "\n\n"]  // Code/section boundaries
  }
}
```

**Ollama models:**
```json
{
  "parameters": {
    "temperature": 0.0,      // Deterministic
    "num_ctx": 8192,         // Match model's context
    "num_predict": 512,      // Output limit
    "repeat_penalty": 1.1    // Reduce repetition
  }
}
```

### 5. Test Instances After Creation

Always test new instances:

```bash
# Create instance
INST_ID=$(curl -sS -X POST "$BASE_URL/v1/admin/models/instances" \
  -H "..." -d '{...}' | jq -r '.id')

# Immediate test
curl -X POST "$BASE_URL/v1/admin/models/instances/$INST_ID/tests" \
  -H "..." \
  -d '{"prompt": "ping", "temperature": 0.0, "max_tokens": 32}'
```

### 6. Use Tenant Scoping for Multi-Tenancy

Isolate instances per tenant:

```bash
# Create tenant-scoped instance
curl -X POST "$BASE_URL/v1/admin/models/instances" \
  -H "X-Tenant-Id: tenant-uuid" \
  -d '{
    "tenant_id": "tenant-uuid",
    "..."
  }'

# Set tenant-specific default
curl -X PATCH "$BASE_URL/v1/admin/models/defaults" \
  -H "X-Tenant-Id: tenant-uuid" \
  -d '{"chat": {"instance_id": "inst-uuid"}}'
```

### 7. Handle Provider Errors Gracefully

Always check status codes and retry:

```bash
# Retry logic with exponential backoff
for i in {1..3}; do
  RESPONSE=$(curl -sS -w "\n%{http_code}" \
    -X POST "$BASE_URL/v1/admin/models/instances" \
    -H "..." -d '{...}')
  
  BODY=$(echo "$RESPONSE" | head -n -1)
  STATUS=$(echo "$RESPONSE" | tail -n 1)
  
  if [ "$STATUS" = "201" ] || [ "$STATUS" = "200" ]; then
    echo "Success: $BODY"
    break
  elif [ "$STATUS" = "502" ] || [ "$STATUS" = "504" ]; then
    echo "Retry $i: Provider error ($STATUS)"
    sleep $((i * 2))  # Exponential backoff
  else
    echo "Fatal error ($STATUS): $BODY"
    exit 1
  fi
done
```

### 8. Monitor Latency and Usage

Track test metrics for capacity planning:

```bash
curl -X POST "$BASE_URL/v1/admin/models/instances/$INST_ID/tests" \
  -H "..." -d '{...}' | jq '{
    model: .model,
    latency_ms: .latency_ms,
    prompt_tokens: .usage.prompt_tokens,
    completion_tokens: .usage.completion_tokens,
    total_tokens: .usage.total_tokens
  }'
```

### 9. Use Pagination for Large Datasets

Always paginate when listing many instances:

```bash
# Efficient pagination
page_token=""
while true; do
  RESPONSE=$(curl -sS "$BASE_URL/v1/admin/models/instances?page_size=50&page_token=$page_token" \
    -H "Authorization: Bearer $TOKEN")
  
  # Process page
  echo "$RESPONSE" | jq '.items[]'
  
  # Check for next page
  page_token=$(echo "$RESPONSE" | jq -r '.next_page_token // empty')
  [ -z "$page_token" ] && break
done
```

### 10. Clean Up Unused Instances

Remove instances no longer needed:

```bash
# List all instances
INSTANCES=$(curl -sS "$BASE_URL/v1/admin/models/instances" \
  -H "Authorization: Bearer $TOKEN" \
  | jq -r '.items[].id')

# Delete unused (example: all but default)
DEFAULT=$(curl -sS "$BASE_URL/v1/admin/models/defaults" \
  -H "Authorization: Bearer $TOKEN" \
  | jq -r '.chat.instance_id')

for INST_ID in $INSTANCES; do
  [ "$INST_ID" = "$DEFAULT" ] && continue
  curl -X DELETE "$BASE_URL/v1/admin/models/instances/$INST_ID" \
    -H "Authorization: Bearer $TOKEN"
done
```

---

## Appendix: cURL Template Scripts

### create_gpt4o_instance.sh

```bash
#!/bin/bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
TOKEN="${TOKEN:-your_token_here}"
PROVIDER_ID="${PROVIDER_ID:-your_provider_uuid}"

curl -X POST "$BASE_URL/v1/admin/models/instances" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{
    "provider_id": "'"$PROVIDER_ID"'",
    "instance_name": "gpt-4o",
    "model_id": "gpt-4o",
    "model_uri": null,
    "tenant_id": null,
    "parameters": {
      "temperature": 0.2,
      "top_p": 1.0,
      "max_tokens": 2048,
      "stop": ["```", "\n\n"]
    },
    "context_window": 128000,
    "modalities": ["text", "vision"],
    "description": "OpenAI GPT-4o (128k context)"
  }' | jq
```

### set_default_model.sh

```bash
#!/bin/bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
TOKEN="${TOKEN:-your_token_here}"
INSTANCE_ID="${1:-}"

if [ -z "$INSTANCE_ID" ]; then
  echo "Usage: $0 <instance_id>"
  exit 1
fi

curl -X PATCH "$BASE_URL/v1/admin/models/defaults" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "chat": {
      "instance_id": "'"$INSTANCE_ID"'"
    }
  }' | jq
```

### test_instance.sh

```bash
#!/bin/bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
TOKEN="${TOKEN:-your_token_here}"
INSTANCE_ID="${1:-}"
PROMPT="${2:-Explain quantum computing in one sentence.}"

if [ -z "$INSTANCE_ID" ]; then
  echo "Usage: $0 <instance_id> [prompt]"
  exit 1
fi

curl -X POST "$BASE_URL/v1/admin/models/instances/$INSTANCE_ID/tests" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "'"$PROMPT"'",
    "temperature": 0.0,
    "max_tokens": 64
  }' | jq '{
    model: .model,
    output: .output,
    latency_ms: .latency_ms,
    tokens: .usage.total_tokens
  }'
```

---

## Changelog

- **2025-10-17**: Initial comprehensive guide with realistic examples
  - Added OpenAI, Azure OpenAI, OpenRouter, Ollama examples
  - Documented schema constraints (modalities, context_window, parameters)
  - Clarified provider_id (UUID) and tenant_id (nullable) semantics
  - Added Idempotency-Key documentation
  - Included ETag/304 caching examples
  - Documented error handling with RFC 7807 format
  - Added best practices and cURL templates

---

## Related Documentation

- [Providers API Guide](./PROVIDERS_API_COMPLETE_SUMMARY.md)
- [OpenAPI Specification](../api/openapi.json)
- [API Standardization Plan](./API_STANDARDIZATION_PLAN.md)
- [Environment Variables](./environment-variables.md)
