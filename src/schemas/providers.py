"""
Pydantic schemas for LLM Provider management API.

Defines canonical request/response models for provider CRUD operations,
including proper validation, enums, pagination, and secret redaction.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------- Enums ----------


class ProviderType(str, Enum):
    """Allowed provider types for LLM integration."""

    OPENAI_COMPATIBLE = "openai_compatible"
    CUSTOM = "custom"


# ---------- Nested Configuration Models ----------


class Timeouts(BaseModel):
    """HTTP timeout configuration for provider requests."""

    model_config = ConfigDict(extra="allow")

    connect: float | None = Field(default=2.0, ge=0, description="Connection timeout in seconds")
    read: float | None = Field(default=30.0, ge=0, description="Read timeout in seconds")
    write: float | None = Field(default=10.0, ge=0, description="Write timeout in seconds")


class TLSConfig(BaseModel):
    """TLS/SSL configuration for provider connections."""

    model_config = ConfigDict(extra="allow")

    verify: bool | None = Field(default=True, description="Whether to verify SSL certificates")


class Paths(BaseModel):
    """API path configuration for provider endpoints."""

    model_config = ConfigDict(extra="allow")

    chat_completions: str | None = Field(
        default="/v1/chat/completions", description="OpenAI-compatible chat completions path"
    )
    completions: str | None = Field(default=None, description="Optional raw completions path (provider-specific)")
    embeddings: str | None = Field(default="/v1/embeddings", description="Embeddings endpoint path")


class RequestTemplates(BaseModel):
    """Request body templates for different operation types."""

    model_config = ConfigDict(extra="allow")

    chat: str | None = Field(default=None, description="Template for chat-completions style request")
    completion: str | None = Field(default=None, description="Legacy singular completion template")
    completions: str | None = Field(default=None, description="Preferred template for completions requests")
    embeddings: str | None = Field(default=None, description="Template for embeddings request body")


class ResponseExtract(BaseModel):
    """JMESPath extractors for parsing provider responses."""

    model_config = ConfigDict(extra="allow")

    text_jmespath: str | None = Field(default=None, description="JMESPath to extract text output (first choice)")
    output: str | None = Field(
        default=None, description="Alias for text extraction when spec uses response_extract.completions.output"
    )
    usage_prompt: str | None = Field(default=None, description="JMESPath for prompt tokens")
    usage_completion: str | None = Field(default=None, description="JMESPath for completion tokens")
    usage_total: str | None = Field(default=None, description="JMESPath for total tokens")
    embedding: str | None = Field(default=None, description="JMESPath for embedding vector")


class AuthConfig(BaseModel):
    """Authentication configuration for provider."""

    model_config = ConfigDict(extra="allow")

    scheme: str | None = Field(default=None, description="Auth scheme (e.g., 'bearer', 'basic')")
    token: str | None = Field(default=None, description="Auth token (will be redacted in responses)")


class ProviderConfig(BaseModel):
    """Provider-specific configuration settings.

    Accepts arbitrary provider-specific keys to support custom configurations.
    Redaction rules apply to: api_key, headers.authorization, auth.token.
    """

    model_config = ConfigDict(extra="allow")

    base_url: str | None = Field(default=None, description="HTTP base URL for the provider")
    api_key: str | None = Field(default=None, description="API key (will be redacted in responses)")
    headers: dict[str, Any] | None = Field(default=None, description="Custom HTTP headers")
    auth: AuthConfig | None = Field(default=None, description="Authentication configuration")
    timeouts: Timeouts | None = Field(default=None, description="Request timeout settings")
    tls: TLSConfig | None = Field(default=None, description="TLS/SSL settings")
    paths: Paths | None = Field(default=None, description="Custom API path overrides")
    request_templates: RequestTemplates | None = Field(default=None, description="Request templates")
    response_extract: ResponseExtract | None = Field(default=None, description="Response extraction config")

    @field_validator("base_url")
    @classmethod
    def normalize_base_url(cls, value: str | None) -> str | None:
        """Normalize base_url by stripping trailing slashes."""
        if value is None:
            return None
        stripped = value.strip()
        return stripped.rstrip("/") if stripped else None


# ---------- Health Status ----------


class ProviderHealth(BaseModel):
    """Provider health/reachability status.

    Health information is cached from the last health check and remains stable
    across GET reads unless explicitly refreshed. Health checks are performed:
    - On provider registration (initial check)
    - Periodically by background workers (if configured)
    - Optionally after PATCH operations (implementation-dependent)

    **Source**: Cached result from last health check, not live probe.
    """

    model_config = ConfigDict(extra="allow")

    reachable: bool = Field(..., description="Whether the provider was reachable during last check")
    status: int | None = Field(default=None, description="HTTP status code from last health check (e.g., 200, 503)")
    last_check: float | None = Field(default=None, description="Unix timestamp of last health check")
    latency_ms: int | None = Field(default=None, description="Response latency in milliseconds")
    error: str | None = Field(default=None, description="Error message if unreachable")


# ---------- Core Provider Models ----------


class Provider(BaseModel):
    """Canonical Provider schema used for GET/LIST responses."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(..., description="Unique provider identifier")
    name: str = Field(..., description="Human-friendly provider name")
    type: ProviderType = Field(..., description="Provider type")
    base_url: str | None = Field(default=None, description="HTTP base URL")
    model: str | None = Field(default=None, description="Default model identifier")
    tenant_id: str | None = Field(default=None, description="Tenant scope (null for global)")
    config: ProviderConfig | None = Field(default=None, description="Provider-specific configuration")

    # Secret indicators (never expose actual secrets)
    has_api_key: bool = Field(default=False, description="Whether an API key is configured")

    # Metadata
    created_at: str | float = Field(..., description="Creation timestamp (RFC3339, ISO8601, or Unix epoch)")
    updated_at: str | float = Field(..., description="Last update timestamp (RFC3339, ISO8601, or Unix epoch)")

    # Runtime status
    health: ProviderHealth | None = Field(default=None, description="Current health status")


class ProviderListResponse(BaseModel):
    """Paginated list of providers."""

    items: list[Provider] = Field(default_factory=list, description="List of providers")
    next_page_token: str | None = Field(default=None, description="Token for next page (if available)")
    total: int | None = Field(default=None, description="Total count of providers (optional)")


# ---------- Request Models ----------


class RegisterProviderRequest(BaseModel):
    """Request to register a new provider."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "name": "production-openai",
                    "type": "openai_compatible",
                    "base_url": "https://api.openai.com/v1",
                    "model": "gpt-4",
                    "api_key": "sk-proj-...",
                    "tenant_id": None,
                    "config": {"timeouts": {"connect": 5.0, "read": 30.0}, "headers": {"X-Custom-Header": "value"}},
                },
                {
                    "name": "local-ollama",
                    "type": "openai_compatible",
                    "base_url": "http://localhost:11434/v1",
                    "model": "llama2",
                    "api_key": None,
                    "tenant_id": "tenant-123",
                    "config": {"timeouts": {"connect": 2.0, "read": 60.0}},
                },
            ]
        },
    )

    name: str = Field(
        ..., min_length=1, max_length=255, description="Provider name", examples=["production-openai", "local-ollama"]
    )
    type: ProviderType = Field(..., description="Provider type", examples=["openai_compatible"])
    base_url: str | None = Field(
        default=None,
        description="HTTP base URL (required for openai_compatible)",
        examples=["https://api.openai.com/v1", "http://localhost:11434/v1"],
    )
    model: str | None = Field(default=None, description="Default model identifier", examples=["gpt-4", "llama2"])
    api_key: str | None = Field(default=None, description="API key for authentication", examples=["sk-proj-..."])
    tenant_id: str | None = Field(
        default=None, description="Tenant scope (null for global)", examples=[None, "tenant-123"]
    )
    config: dict[str, Any] | None = Field(
        default=None,
        description="Provider-specific configuration (paths, timeouts, etc.)",
        examples=[{"timeouts": {"connect": 5.0, "read": 30.0}}],
    )

    @field_validator("base_url")
    @classmethod
    def validate_base_url_required(cls, value: str | None, info) -> str | None:
        """Validate base_url is present for openai_compatible providers and is a valid URL."""
        if value:
            value = value.strip().rstrip("/")
            # Validate it's a proper HTTP/HTTPS URL
            try:
                # Use Pydantic's URL validation
                from pydantic import AnyHttpUrl

                parsed = AnyHttpUrl(value)
                if parsed.scheme not in ("http", "https"):
                    raise ValueError("base_url must use http or https scheme")
            except Exception as e:
                raise ValueError(f"Invalid base_url format: {e}")

        # Check if type is openai_compatible (info.data contains other validated fields)
        provider_type = info.data.get("type")
        if provider_type == ProviderType.OPENAI_COMPATIBLE and not value:
            raise ValueError("base_url is required for openai_compatible providers")

        return value

    @field_validator("type")
    @classmethod
    def validate_provider_type(cls, value: str) -> ProviderType:
        """Ensure type is a valid ProviderType enum value."""
        # Pydantic already validates enum membership, but add explicit check for clarity
        if not isinstance(value, ProviderType):
            # Try to coerce string to enum
            try:
                return ProviderType(value)
            except ValueError:
                allowed = ", ".join([t.value for t in ProviderType])
                raise ValueError(f"Invalid provider type '{value}'. Allowed: {allowed}")
        return value


class UpdateProviderRequest(BaseModel):
    """Request to update an existing provider."""

    model_config = ConfigDict(extra="forbid")

    base_url: str | None = Field(default=None, description="Updated base URL")
    model: str | None = Field(default=None, description="Updated default model")
    api_key: str | None = Field(default=None, description="Updated API key")
    tenant_id: str | None = Field(default=None, description="Updated tenant scope")
    config: dict[str, Any] | None = Field(default=None, description="Updated configuration (merged)")


class SetDefaultProviderRequest(BaseModel):
    """Request to set a provider as default."""

    model_config = ConfigDict(extra="forbid")

    provider_id: str = Field(..., description="Provider ID to set as default")
    tenant_id: str | None = Field(default=None, description="Tenant scope (null for global default)")


# ---------- Response Models ----------


class ActionResponse(BaseModel):
    """Generic action response with success/failure details."""

    model_config = ConfigDict(extra="allow")

    ok: bool = Field(..., description="Whether the operation succeeded")
    message: str = Field(..., description="Human-readable result message")
    details: dict[str, Any] | None = Field(default=None, description="Additional details")
    trace_id: str | None = Field(default=None, description="Distributed trace ID")
    event_id: str | None = Field(default=None, description="Event/provenance ID")


class GetMainProviderResponse(BaseModel):
    """Response from GET /providers/main."""

    ok: bool = Field(..., description="Operation success")
    tenant_id: str | None = Field(default=None, description="Tenant scope queried")
    main: str | None = Field(default=None, description="Main/default provider ID")


# ---------- Error Models ----------


class ProblemDetails(BaseModel):
    """RFC 7807 Problem Details for HTTP APIs."""

    model_config = ConfigDict(extra="allow")

    type: str = Field(default="about:blank", description="Problem type URI")
    title: str = Field(..., description="Short, human-readable summary")
    status: int = Field(..., description="HTTP status code")
    detail: str | None = Field(default=None, description="Detailed explanation")
    instance: str | None = Field(default=None, description="URI reference to specific occurrence")
    extensions: dict[str, Any] | None = Field(
        default=None, description="Additional problem-specific context (correlation_id, field errors, etc.)"
    )


class ValidationErrorDetail(BaseModel):
    """Field-level validation error detail."""

    loc: list[str] = Field(..., description="Field location path")
    msg: str = Field(..., description="Error message")
    type: str = Field(..., description="Error type")


class ValidationProblemDetails(ProblemDetails):
    """Problem details for validation errors (422)."""

    errors: list[ValidationErrorDetail] = Field(
        default_factory=list, description="List of field-level validation errors"
    )
