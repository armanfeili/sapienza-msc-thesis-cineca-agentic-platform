# Utils Package Documentation

## Overview

The `src/utils/` package provides essential utility functions and helpers for the Cineca Agentic Platform. This package contains cross-cutting concerns including HTTP caching, idempotency, data serialization, pagination, authentication helpers, provider resolution, and testing utilities.

## Architecture

### Design Principles

- **Modular**: Each utility module focuses on a single responsibility
- **Type-safe**: Full type annotations with modern Python typing
- **Testable**: Pure functions where possible, dependency injection for external services
- **Performance-conscious**: Efficient algorithms with caching where appropriate
- **Standards-compliant**: Follows RFC specifications and industry best practices

### Module Organization

```
src/utils/
├── deprecation.py      # HTTP deprecation headers (RFC 8594)
├── etag.py            # ETag generation and validation (RFC 7232)
├── idempotency.py      # Request idempotency with Redis/PostgreSQL
├── jsonable.py        # JSON serialization for database persistence
├── pagination.py      # Stateless pagination with ETag support
├── principal.py       # User identity and permission serialization
├── provider_resolver.py # LLM provider configuration resolution
├── run_output.py      # Agent run output normalization
└── test_helpers.py    # Testing utilities for LLM interactions
```

## Core Utilities

### 1. Deprecation Headers (`deprecation.py`)

**Purpose**: Generate standardized HTTP deprecation headers following RFC 8594.

**Key Features**:
- RFC 8594 compliant deprecation signaling
- Automatic sunset date calculation
- Link headers for successor resources
- Configurable deprecation periods

**Core Functions**:
```python
def deprecation_headers(
    replacement: str | None = None,
    sunset: str | None = None,
    *,
    sunset_days: int = 45
) -> dict[str, str]:
    """Return standardized Deprecation and Sunset headers."""
```

**Usage**:
```python
# API endpoint deprecation
headers = deprecation_headers(
    replacement="/api/v2/users",
    sunset_days=90
)
# Returns: {"Deprecation": "true", "Sunset": "Wed, 01 Jan 2025 00:00:00 GMT", "Link": '<api/v2/users>; rel="successor-version"'}
```

**Standards Compliance**:
- RFC 8594: Deprecation HTTP Header Field
- RFC 1123: HTTP Date format
- RFC 8288: Link header relations

### 2. ETag Generation (`etag.py`)

**Purpose**: Generate and validate HTTP ETags for caching and conditional requests (RFC 7232).

**Key Features**:
- SHA-256 content hashing for strong ETags
- Weak ETag support for semantic equivalence
- List/collection ETag generation
- If-None-Match header validation
- Content-addressable identifiers

**Core Functions**:
```python
def generate_etag(obj: Any, weak: bool = False) -> str:
    """Generate ETag from JSON-serializable object."""
    
def etag_for_list(items: list[Any], weak: bool = False) -> str:
    """Generate ETag for list of items."""
    
def validate_etag(if_none_match: str | None, current_etag: str) -> bool:
    """Validate ETag against If-None-Match header."""
```

**Usage**:
```python
# Single resource ETag
user_data = {"id": 123, "name": "Alice"}
etag = generate_etag(user_data)  # '"a1b2c3..."'

# List ETag
users = [{"id": 1}, {"id": 2}]
list_etag = etag_for_list(users)  # '"d4e5f6..."'

# Conditional request validation
if validate_etag(request.headers.get("If-None-Match"), current_etag):
    return Response(status_code=304)  # Not Modified
```

**ETag Types**:
- **Strong ETag**: `"abc123"` - byte-for-byte identical content
- **Weak ETag**: `W/"abc123"` - semantically equivalent content
- **List ETag**: Hash of combined item representations

### 3. Idempotency (`idempotency.py`)

**Purpose**: Provide request idempotency for FastAPI endpoints using Redis/PostgreSQL storage.

**Key Features**:
- Redis-backed caching with TTL expiration
- In-memory fallback for testing
- FastAPI Request object inspection
- Response envelope storage and replay
- Automatic signature preservation

**Core Decorator**:
```python
def idempotent(key_fn: Callable[..., str], ttl: int = 24 * 3600) -> Callable:
    """Decorator factory for idempotent endpoints."""
```

**Usage**:
```python
@idempotent(
    key_fn=lambda idempotency_key, user_id: f"user_{user_id}_{idempotency_key}",
    ttl=3600
)
async def create_resource(request: Request, user_id: str, data: dict):
    # Expensive operation - safe to retry
    return await expensive_operation(data)
```

**Key Features**:
- **Automatic Deduplication**: Prevents duplicate processing of same request
- **TTL Expiration**: Configurable cache lifetime (default 24 hours)
- **Response Replay**: Stores and replays exact response on retry
- **Header Inspection**: Extracts Idempotency-Key from request headers
- **Error Handling**: Graceful fallback on storage failures

**Storage Envelope**:
```python
{
    "status": 200,
    "headers": {"Content-Type": "application/json"},
    "body": {"id": "123", "created": true}
}
```

### 4. JSON Serialization (`jsonable.py`)

**Purpose**: Convert Python objects to JSON-serializable forms for database persistence.

**Key Features**:
- Comprehensive type conversion
- RFC 3339 timestamp formatting
- UUID and Decimal handling
- Recursive processing of nested structures
- Path and Enum support

**Core Function**:
```python
def to_jsonable(obj: Any) -> Any:
    """Convert object to JSON-serializable form."""
```

**Supported Conversions**:
```python
# Datetime objects
datetime(2024, 1, 1, 12, 0, 0) → "2024-01-01T12:00:00Z"

# UUID objects  
UUID("12345678-1234-5678-1234-567812345678") → "12345678-1234-5678-1234-567812345678"

# Decimal objects
Decimal("123.45") → 123.45

# Enum objects
MyEnum.VALUE → "VALUE"

# Path objects
Path("/tmp/file.txt") → "/tmp/file.txt"

# Collections
{"key": datetime(...)} → {"key": "2024-01-01T12:00:00Z"}
```

**Usage**:
```python
# Database storage preparation
user_data = {
    "id": UUID("1234..."),
    "created_at": datetime.now(),
    "balance": Decimal("99.99")
}

json_ready = to_jsonable(user_data)
# Can now be safely stored in JSONB column
```

### 5. Pagination (`pagination.py`)

**Purpose**: Stateless pagination utilities with ETag support for API responses.

**Key Features**:
- Offset-based pagination
- ETag generation for cache validation
- Context-aware ETag computation
- Memory-efficient large dataset handling

**Core Functions**:
```python
def make_page(
    items: list[Any], 
    page_size: int = 50, 
    page_token: str | None = None
) -> tuple[list[Any], str | None]:
    """Paginate list with continuation token."""
    
def compute_etag(obj: Any, context: dict[str, Any] | None = None) -> str:
    """Compute weak ETag for response caching."""
```

**Usage**:
```python
# API pagination
def get_users(page_token: str | None = None):
    all_users = get_all_users_from_db()
    
    page_items, next_token = make_page(
        all_users, 
        page_size=50, 
        page_token=page_token
    )
    
    # Generate ETag for caching
    etag = compute_etag({
        "users": page_items,
        "count": len(page_items)
    }, context={"endpoint": "users", "page_size": 50})
    
    return {
        "users": page_items,
        "next_page_token": next_token
    }, {"ETag": etag}
```

### 6. Principal Identity (`principal.py`)

**Purpose**: Extract and serialize user identity information for downstream services.

**Key Features**:
- Multiple identity field fallback
- Permission serialization
- Tenant and role extraction
- JSON-serializable output

**Core Functions**:
```python
def principal_identity(p: Any) -> str:
    """Extract human-friendly principal identifier."""
    
def serialize_principal(user: Any, tenant_id: str | None = None) -> dict[str, Any]:
    """Create JSON-serializable principal payload."""
```

**Identity Resolution Order**:
1. `sub` (subject claim)
2. `email`
3. `name`
4. `username`
5. `subject` (alias)
6. `"unknown"` (fallback)

**Usage**:
```python
# From JWT token or auth object
user = request.user  # or decoded_jwt

identity = principal_identity(user)  # "alice@example.com"

payload = serialize_principal(user, tenant_id="tenant_123")
# {
#   "id": "alice@example.com",
#   "sub": "alice@example.com", 
#   "scopes": ["read", "write"],
#   "permissions": ["users:read", "users:write"],
#   "tenant_id": "tenant_123",
#   "roles": ["admin"]
# }
```

### 7. Provider Resolution (`provider_resolver.py`)

**Purpose**: Runtime resolution of LLM provider configurations with environment overrides.

**Key Features**:
- Ollama provider detection
- Base URL resolution with fallbacks
- Timeout configuration by provider
- Model ID translation
- Debug logging utilities

**Core Functions**:
```python
def is_ollama_provider(provider: Any) -> bool:
    """Detect Ollama provider configuration."""
    
def resolve_provider_base_url(provider: Any) -> str | None:
    """Get effective base URL with overrides."""
    
def timeout_for_provider(provider: Any) -> httpx.Timeout:
    """Get provider-specific timeout configuration."""
    
def resolve_upstream_model_id(provider: Any, ...) -> str | None:
    """Translate logical model IDs to provider-specific IDs."""
```

**Ollama Integration**:
```python
# Environment override
OLLAMA_BASE_URL=http://custom-ollama:11434

# Automatic detection
provider = {"type": "ollama", "base_url": "http://localhost:11434"}
is_ollama = is_ollama_provider(provider)  # True

# Timeout handling
timeout = timeout_for_provider(provider)  # 60s for Ollama
```

**Model Mapping**:
```python
# Logical → Provider mapping
settings.ollama_model_map = {
    "phi3-mini": "phi3:3.8b",
    "qwen2.5-7b": "qwen2.5:7b"
}
```

### 8. Run Output Normalization (`run_output.py`)

**Purpose**: Normalize agent run outputs to schema-compliant structures for database storage.

**Key Features**:
- Binary data decoding
- JSON parsing with fallbacks
- Pydantic/BaseModel support
- Dataclass conversion
- Type coercion to dict/list/None

**Core Function**:
```python
def normalize_run_output(value: Any) -> dict | list | None:
    """Coerce arbitrary output to schema-compliant form."""
```

**Normalization Rules**:
```python
# Binary data
b'{"key": "value"}' → {"key": "value"}

# JSON strings
'{"text": "hello"}' → {"text": "hello"}

# Pydantic models
MyModel(id=123) → {"id": 123}

# Dataclasses
@dataclass
class Result:
    output: str
Result("hello") → {"output": "hello"}

# Primitives
"hello world" → {"text": "hello world"}
42 → {"text": "42"}
```

**Usage**:
```python
# Agent orchestrator output
raw_output = await orchestrator.run(goal)

# Normalize for database storage
normalized = normalize_run_output(raw_output)
# Always dict, list, or None - safe for JSONB
```

### 9. Test Helpers (`test_helpers.py`)

**Purpose**: Testing utilities for LLM interactions with model-specific optimizations.

**Key Features**:
- Prompt hashing for log privacy
- Model-aware system message generation
- Chat format normalization
- Stop sequence configuration
- Response text extraction and cleanup
- Usage estimation

**Core Functions**:
```python
def normalize_request_to_messages(...) -> list[dict[str, str]]:
    """Convert prompts to OpenAI chat format."""
    
def extract_text_from_response(response_data: Any, model_id: str) -> tuple[str, dict]:
    """Extract clean text and usage from provider responses."""
    
def normalize_output_text(text: str, model_id: str) -> str:
    """Clean LLM output text."""
```

**Model-Specific Handling**:
```python
# Qwen models - prevent conversation chains
build_system_message("qwen2.5:3b", one_sentence=True)
# "You are a helpful assistant. Answer in one short sentence. Do not list options. Do not ask follow-up questions."

# Phi-3 models - simple instructions work better
build_system_message("phi3:mini", format_hint="poem")
# "You write poetry directly without explanations."
```

**Response Processing**:
```python
# Handle various response formats
response = {
    "choices": [{"message": {"content": "Hello world"}}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5}
}

text, usage = extract_text_from_response(response, "gpt-4")
# ("Hello world", {"prompt_tokens": 10, "completion_tokens": 5})
```

**Text Cleanup**:
- Remove chat template tokens (`<|assistant|>`, `<|end|>`)
- Strip MCQ patterns (`A) `, `B.`)
- Remove code fences
- Collapse multiple blank lines
- Handle Phi-3 JSON quirks

## Integration Patterns

### HTTP Caching Strategy

```python
# Combine ETags and pagination
@app.get("/api/users")
async def get_users(page_token: str | None = None):
    users, next_token = paginate_users(page_token)
    
    # Context-aware ETag
    etag = compute_etag({
        "users": users,
        "endpoint": "users"
    }, context={"page_size": 50})
    
    # Conditional response
    if validate_etag(request.headers.get("If-None-Match"), etag):
        return Response(status_code=304)
    
    return JSONResponse(
        {"users": users, "next_page_token": next_token},
        headers={"ETag": etag}
    )
```

### Idempotent Operations

```python
# Payment processing with idempotency
@router.post("/payments")
@idempotent(
    key_fn=lambda key, user_id: f"payment_{user_id}_{key}",
    ttl=3600 * 24  # 24 hours
)
async def process_payment(payment: PaymentRequest, user_id: str):
    # Expensive operation - safe to retry
    result = await payment_service.charge(payment)
    return {"payment_id": result.id, "status": "completed"}
```

### Provider-Aware Requests

```python
# LLM provider abstraction
async def call_llm(provider_config: dict, prompt: str, model: str):
    base_url = resolve_provider_base_url(provider_config)
    timeout = timeout_for_provider(provider_config)
    mapped_model = resolve_upstream_model_id(
        provider_config, model, model, None
    )
    
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
        response = await client.post("/chat/completions", json={
            "model": mapped_model,
            "messages": [{"role": "user", "content": prompt}]
        })
        
        debug_log_provider_call(
            logger, event="llm_call",
            base_url=base_url, resolved_model=model, mapped_model=mapped_model,
            status_code=response.status_code
        )
        
        return response.json()
```

## Configuration

### Environment Variables

```bash
# Provider configuration
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_TIMEOUT_SECS=60

# Idempotency
REDIS_URL=redis://localhost:6379

# Pagination
DEFAULT_PAGE_SIZE=50

# Testing
TEST_MODEL_TIMEOUT=30
```

### Settings Integration

```python
from src.config import settings

# Provider resolution
ollama_url = settings.resolve_ollama_base_url()
model_map = settings.effective_ollama_model_map

# Timeouts
default_timeout = DEFAULT_HTTPX_TIMEOUT
ollama_timeout = timeout_for_provider({"type": "ollama"})
```

## Testing

### Unit Tests

```python
def test_etag_generation():
    data = {"id": 123, "name": "test"}
    etag = generate_etag(data)
    assert etag.startswith('"')
    assert etag.endswith('"')

def test_pagination():
    items = list(range(100))
    page, next_token = make_page(items, page_size=10)
    assert len(page) == 10
    assert next_token == "10"

def test_jsonable_conversion():
    data = {"date": datetime(2024, 1, 1), "uuid": UUID("1234")}
    result = to_jsonable(data)
    assert isinstance(result["date"], str)
    assert isinstance(result["uuid"], str)
```

### Integration Tests

```python
@pytest.mark.asyncio
async def test_idempotent_decorator():
    call_count = 0
    
    @idempotent(lambda key: f"test_{key}")
    async def test_func(value: int):
        nonlocal call_count
        call_count += 1
        return {"result": value * 2}
    
    # First call
    result1 = await test_func(5)
    assert result1 == {"result": 10}
    assert call_count == 1
    
    # Second call with same key (should replay)
    result2 = await test_func(5)
    assert result2 == {"result": 10}
    assert call_count == 1  # Not called again
```

## Performance Considerations

### Caching Strategies

- **ETag Caching**: Reduces server load for unchanged resources
- **Idempotency**: Prevents duplicate expensive operations
- **Provider Resolution**: Caches resolved configurations

### Memory Management

- **Streaming**: Large responses handled via streaming
- **Pagination**: Prevents loading full datasets
- **Cleanup**: TTL-based expiration for cached data

### Optimization Tips

```python
# Batch ETag computation
etags = [generate_etag(item) for item in items]
list_etag = etag_for_list(etags)  # More efficient than full re-hash

# Efficient pagination
def paginate_efficiently(query, page_size, offset):
    return query.offset(offset).limit(page_size).all()
```

## Security Considerations

### Input Validation

```python
# ETag validation prevents cache poisoning
def safe_etag_validation(if_none_match, current_etag):
    if not if_none_match or not current_etag:
        return False
    # Strip quotes and validate format
    return validate_etag(if_none_match, current_etag)
```

### Idempotency Keys

- **Uniqueness**: Keys must be unique per operation
- **Entropy**: Use sufficient randomness to prevent collisions
- **Expiration**: TTL prevents infinite storage growth

### Provider Security

```python
# Validate provider configurations
def validate_provider_config(config: dict) -> bool:
    required = ["type", "base_url"]
    return all(key in config for key in required)
```

## Migration Notes

### Version Compatibility

- **Python 3.9+**: Full type annotation support
- **FastAPI**: Request object inspection for idempotency
- **httpx**: Modern async HTTP client for providers

### Breaking Changes

- **ETag Format**: Now uses SHA-256 (was MD5 in legacy versions)
- **Timeout Units**: Now in seconds (was milliseconds)
- **Principal Fields**: Added tenant_id and roles fields

## Future Enhancements

### Planned Features

- **Compression**: Response compression for large payloads
- **Rate Limiting**: Request rate limiting utilities
- **Metrics**: Prometheus metrics integration
- **Tracing**: Distributed tracing support

### Performance Optimizations

- **Connection Pooling**: HTTP connection reuse
- **Async Caching**: Async Redis operations
- **Batch Operations**: Bulk ETag generation