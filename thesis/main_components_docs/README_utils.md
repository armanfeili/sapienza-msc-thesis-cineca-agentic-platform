# Utilities Framework

The utilities package provides common helper functions, decorators, and utilities used throughout the Cineca Agentic Platform. These utilities focus on cross-cutting concerns like pagination, idempotency, data normalization, and provider resolution.

## Architecture Overview

The utilities framework follows these design principles:

- **Pure Functions**: Utilities are stateless and side-effect free where possible
- **Type Safety**: Comprehensive type hints and Pydantic integration
- **Performance Focused**: Minimal overhead and efficient implementations
- **Defensive Programming**: Graceful error handling and fallbacks
- **Modular Design**: Single-responsibility utilities that can be used independently

## Core Components

### 1. Pagination (`pagination.py`)

Stateless pagination utilities with ETag support for efficient caching.

#### Pagination
```python
from src.utils.pagination import make_page

# Paginate a list
items = ["item1", "item2", "item3", "item4", "item5"]
page_items, next_token = make_page(
    items=items,
    page_size=2,
    page_token="0"  # Start from beginning
)
# Returns: (["item1", "item2"], "2")

# Get next page
page_items, next_token = make_page(
    items=items,
    page_size=2,
    page_token="2"
)
# Returns: (["item3", "item4"], "4")
```

#### ETag Generation
```python
from src.utils.pagination import compute_etag

# Generate ETag for response caching
etag = compute_etag(
    obj={"data": "value"},
    context={"route": "users", "filter": "active"}
)
# Returns: W/"sha256_hash_here"
```

### 2. Idempotency (`idempotency.py`)

Decorator-based idempotency support for API endpoints with Redis/in-memory storage.

#### Idempotent Operations
```python
from src.utils.idempotency import idempotent

def make_key(idempotency_key: str, user_id: str) -> str:
    return f"user:{user_id}:action:{idempotency_key}"

@idempotent(key_fn=make_key, ttl=3600)
async def create_resource(user_id: str, data: dict) -> dict:
    # This operation will only execute once per idempotency key
    return await database.create(data)
```

#### FastAPI Integration
```python
from fastapi import Request
from src.utils.idempotency import idempotent

def payment_key(idempotency_key: str, request: Request, amount: float) -> str:
    return f"payment:{request.headers.get('user-id')}:{idempotency_key}"

@router.post("/pay")
@idempotent(key_fn=payment_key, ttl=86400)  # 24 hours
async def process_payment(request: Request, amount: float):
    # Safe for client retries
    return await payment_service.charge(amount)
```

### 3. Provider Resolution (`provider_resolver.py`)

Runtime provider configuration resolution with Ollama-specific handling.

#### Provider Detection
```python
from src.utils.provider_resolver import is_ollama_provider, resolve_provider_base_url

# Check if provider is Ollama
if is_ollama_provider(provider_config):
    print("Ollama provider detected")

# Get effective base URL
base_url = resolve_provider_base_url(provider_config)
# Handles environment overrides and defaults
```

#### Timeout Configuration
```python
from src.utils.provider_resolver import timeout_for_provider

# Get appropriate timeout for provider
timeout = timeout_for_provider(provider_config)
# Ollama gets longer timeouts, others use defaults
```

#### Model ID Resolution
```python
from src.utils.provider_resolver import resolve_upstream_model_id

# Translate logical model IDs to provider-specific IDs
upstream_id = resolve_upstream_model_id(
    provider=provider_config,
    resolved_model="gpt-4",
    requested_model="turbo",
    instance=instance_config
)
```

### 4. Run Output Normalization (`run_output.py`)

Schema-compliant output normalization for agent runs and orchestrator results.

#### Output Normalization
```python
from src.utils.run_output import normalize_run_output

# Normalize various output types to dict/list/None
normalized = normalize_run_output(raw_output)

# Examples:
normalize_run_output({"key": "value"})        # {"key": "value"}
normalize_run_output([1, 2, 3])              # [1, 2, 3]
normalize_run_output("text response")        # {"text": "text response"}
normalize_run_output(42)                     # {"text": "42"}
normalize_run_output(None)                   # None
normalize_run_output(b'{"json": "data"}')    # {"json": "data"}
```

#### Pydantic Integration
```python
from pydantic import BaseModel
from src.utils.run_output import normalize_run_output

class RunResult(BaseModel):
    output: dict | list | None

# Normalize before validation
raw_result = get_orchestrator_output()
normalized_result = RunResult(output=normalize_run_output(raw_result))
```

### 5. Principal Utilities (`principal.py`)

User identity and context management utilities.

#### Principal Handling
```python
from src.utils.principal import extract_user_id, get_tenant_from_principal

# Extract user ID from various principal formats
user_id = extract_user_id(principal_dict_or_obj)

# Get tenant context
tenant_id = get_tenant_from_principal(principal)
```

### 6. JSON Utilities (`jsonable.py`)

JSON serialization helpers with error handling and type coercion.

#### Safe JSON Operations
```python
from src.utils.jsonable import safe_json_dumps, safe_json_loads

# Safe serialization with fallbacks
json_str = safe_json_dumps({"data": "value"})
# Handles circular references, non-serializable objects

# Safe deserialization
data = safe_json_loads(json_string)
# Returns None on parse errors instead of raising
```

### 7. ETag Support (`etag.py`)

HTTP ETag generation and validation utilities.

#### ETag Operations
```python
from src.utils.etag import generate_etag, validate_etag

# Generate strong ETag
etag = generate_etag(content_bytes_or_dict)

# Validate against If-None-Match
if validate_etag(request.headers.get("If-None-Match"), current_etag):
    return Response(status_code=304)  # Not Modified
```

### 8. Deprecation Helpers (`deprecation.py`)

Utilities for managing API deprecation and migration.

#### Deprecation Warnings
```python
from src.utils.deprecation import deprecated, warn_deprecated

@deprecated("Use new_function() instead", removal_version="2.0.0")
def old_function():
    return "deprecated"

# Manual deprecation warning
warn_deprecated(
    feature="old_endpoint",
    alternative="new_endpoint",
    removal_version="2.0.0"
)
```

### 9. Test Helpers (`test_helpers.py`)

Testing utilities for unit tests and integration tests.

#### Test Fixtures
```python
from src.utils.test_helpers import mock_async_context, async_test

@async_test
async def test_async_function():
    async with mock_async_context():
        result = await async_function()
        assert result is not None
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_BASE_URL` | `http://ollama:11434` | Ollama provider base URL |
| `OLLAMA_TIMEOUT_SECS` | `60` | Ollama request timeout |
| `IDEMPOTENCY_TTL_SECONDS` | `86400` | Default idempotency TTL |

## Usage Examples

### Complete Pagination Implementation
```python
from fastapi import APIRouter, Request, Response
from src.utils.pagination import make_page, compute_etag

router = APIRouter()

@router.get("/items")
async def list_items(
    request: Request,
    page_token: str | None = None,
    page_size: int = 50
):
    # Get all items (in real app, this would be filtered/sorted)
    all_items = await get_all_items()

    # Paginate results
    page_items, next_token = make_page(
        items=all_items,
        page_size=page_size,
        page_token=page_token
    )

    # Generate ETag for caching
    etag = compute_etag(
        obj=page_items,
        context={
            "route": "items",
            "page_size": page_size,
            "total_count": len(all_items)
        }
    )

    # Check If-None-Match
    if request.headers.get("If-None-Match") == etag:
        return Response(status_code=304)

    response_data = {
        "items": page_items,
        "next_page_token": next_token
    }

    return Response(
        content=json.dumps(response_data),
        media_type="application/json",
        headers={"ETag": etag}
    )
```

### Idempotent Payment Processing
```python
from fastapi import APIRouter, Request, HTTPException
from src.utils.idempotency import idempotent

router = APIRouter()

def payment_key(idempotency_key: str, request: Request, amount: float) -> str:
    """Generate unique key for payment idempotency"""
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        raise HTTPException(400, "Missing user ID")
    return f"payment:{user_id}:{idempotency_key}:{amount}"

@router.post("/payments")
@idempotent(key_fn=payment_key, ttl=3600)  # 1 hour TTL
async def process_payment(
    request: Request,
    payment_data: PaymentRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key")
):
    """
    Process payment with automatic idempotency.

    Client can safely retry with same Idempotency-Key.
    """
    # Validate payment data
    if payment_data.amount <= 0:
        raise HTTPException(400, "Invalid amount")

    # Process payment (idempotent operation)
    result = await payment_service.charge(
        user_id=request.headers["X-User-ID"],
        amount=payment_data.amount,
        currency=payment_data.currency
    )

    return {
        "payment_id": result.id,
        "status": "completed",
        "amount": payment_data.amount
    }
```

### Provider-Aware Model Resolution
```python
from src.utils.provider_resolver import (
    resolve_provider_base_url,
    timeout_for_provider,
    resolve_upstream_model_id
)

async def call_model_api(provider: dict, model: str, prompt: str):
    """Make provider-aware API call with proper configuration"""

    # Resolve base URL (handles Ollama overrides)
    base_url = resolve_provider_base_url(provider)

    # Get appropriate timeout
    timeout = timeout_for_provider(provider)

    # Resolve model ID for this provider
    upstream_model = resolve_upstream_model_id(
        provider=provider,
        resolved_model=model,
        requested_model=model,
        instance=None
    )

    # Make API call with resolved configuration
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{base_url}/chat/completions",
            json={
                "model": upstream_model,
                "messages": [{"role": "user", "content": prompt}]
            }
        )

    return response.json()
```

### Output Normalization Pipeline
```python
from src.utils.run_output import normalize_run_output
from src.schemas.agents import RunResponse

async def process_agent_run(run_result: Any) -> RunResponse:
    """Process and normalize agent run output"""

    # Normalize output to schema-compliant format
    normalized_output = normalize_run_output(run_result.output)

    # Extract additional metadata
    metadata = {}
    if hasattr(run_result, 'metrics'):
        metadata.update(run_result.metrics)

    # Create response
    response = RunResponse(
        run_id=run_result.run_id,
        status=run_result.status,
        output=normalized_output,
        started_at=run_result.started_at,
        finished_at=run_result.finished_at,
        metadata=metadata
    )

    return response
```

## Performance Characteristics

- **Pagination**: O(1) slicing operations, no database overhead
- **ETags**: SHA256 hashing (~0.1ms per request)
- **Idempotency**: Redis O(1) operations with TTL expiration
- **Provider Resolution**: In-memory lookups with environment overrides
- **Output Normalization**: Fast type checking and JSON parsing
- **JSON Operations**: Safe fallbacks prevent exceptions

## Error Handling

Utilities follow consistent error handling patterns:

- **Graceful Degradation**: Fall back to safe defaults on errors
- **Logging**: Structured logging for debugging and monitoring
- **Type Safety**: Runtime type checking prevents invalid operations
- **Validation**: Input validation with clear error messages

## Testing

Utilities include comprehensive test helpers:

```python
from src.utils.test_helpers import (
    mock_redis,
    async_test,
    freeze_time
)

@async_test
async def test_idempotent_operation():
    with mock_redis():
        with freeze_time("2024-01-01T00:00:00Z"):
            result1 = await idempotent_function("key1")
            result2 = await idempotent_function("key1")  # Should return cached result
            assert result1 == result2
```

## Integration Points

### FastAPI Integration
```python
from fastapi import FastAPI, Request, Response
from src.utils.etag import generate_etag, validate_etag
from src.utils.idempotency import idempotent

app = FastAPI()

@app.middleware("http")
async def etag_middleware(request: Request, call_next):
    response = await call_next(request)

    if hasattr(response, 'body'):
        etag = generate_etag(response.body)
        response.headers["ETag"] = etag

        # Handle If-None-Match
        if_none_match = request.headers.get("If-None-Match")
        if if_none_match and validate_etag(if_none_match, etag):
            return Response(status_code=304)

    return response
```

### Database Integration
```python
from src.utils.pagination import make_page
from src.utils.etag import generate_etag

async def paginated_query(query, page_token: str | None, page_size: int):
    """Database query with pagination and caching"""

    # Apply pagination at database level for efficiency
    offset = int(page_token) if page_token else 0
    results = await db.execute(query.limit(page_size).offset(offset))

    # Generate next page token
    next_token = str(offset + page_size) if len(results) == page_size else None

    # Generate ETag for result set
    etag = generate_etag(results)

    return {
        "results": results,
        "next_page_token": next_token,
        "etag": etag
    }
```

## Migration and Compatibility

- **Backwards Compatible**: Utility functions maintain API stability
- **Version Pinning**: Explicit version handling where needed
- **Fallback Support**: Safe defaults for missing configurations
- **Deprecation Path**: Clear migration path for deprecated utilities</content>
<parameter name="filePath">/Users/armanfeili/Arman/Sapienza Courses/4-semester/Thesis/ILP-Thesis-2025/Cineca-Agentic-Platform/docs/general/README_utils.md