"""
LLM model and instance management schemas.

This module contains all Pydantic models used for:
- Model instance lifecycle (create, load, list, detail)
- Model testing and health checks
- Default model selection
- Chat completions, text completions, embeddings
- Token usage tracking

All routers that work with LLM models MUST import these schemas.
Do NOT define new Pydantic models in routers - extend this file instead.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---------------- Enums ----------------
class Modality(str, Enum):
    """Supported model modalities."""

    TEXT = "text"
    VISION = "vision"
    AUDIO = "audio"
    TOOL = "tool"


# ---------------- Core Model Info ----------------
class ModelInfo(BaseModel):
    """
    Unified model information schema.

    Used across multiple contexts:
    - Model catalog listings (GET /v1/models)
    - Model instance registry (GET /v1/admin/models/instances)
    - Default model resolution

    Merges fields from routers/model_management.py and routers/models.py.
    """

    id: str | None = Field(None, description="Stable instance identifier (UUID when instance exists)")
    name: str = Field(..., description="Canonical model identifier / instance name")
    provider_id: str | None = Field(None, description="Registered provider identifier (UUID) backing this instance")
    model_id: str | None = Field(
        None, description="Logical model id at the provider (e.g., 'gpt-4o', 'llama3.2:3b-instruct')"
    )
    provider: str | None = Field(None, description="Provider name exposing the model (e.g., 'openai', 'ollama')")
    context_window: int | None = Field(None, description="Maximum context window / token limit")
    modalities: list[str] = Field(
        default_factory=lambda: ["text"], description="Supported modalities (e.g., 'text', 'vision', 'audio')"
    )
    description: str | None = Field(None, description="Short human-friendly description of the model")
    enabled: bool = Field(True, description="Whether the model is enabled for selection")
    loaded: bool | None = Field(None, description="Whether the model instance is currently loaded in runtime")
    default: bool = Field(False, description="Whether this model is the resolved default for selection")


# ---------------- Instance Lifecycle ----------------
class InstanceCreateRequest(BaseModel):
    """
    Legacy instance creation request (from model_management.py).

    NOTE: LoadInstanceRequest is the newer schema with more fields.
    This is kept for backward compatibility with legacy endpoints.
    """

    provider_id: str = Field(..., description="Registered provider identifier (e.g., local-llamacpp)")
    instance_name: str = Field(..., description="Desired logical instance name")
    model_uri: str | None = Field(None, description="Absolute path to a local model file inside the container")
    model_id: str | None = Field(None, description="Logical model id to resolve via provider/manifest")
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="Adapter/runtime parameters (num_ctx, temperature, etc.)"
    )
    tenant_id: str | None = Field(default=None, description="Optional tenant id to scope this instance")
    # Legacy compatibility
    name: str | None = Field(
        None, alias="modelKey", description="Legacy model name (mapped to instance_name if provided)"
    )


class LoadInstanceRequest(BaseModel):
    """
    Request to load/create a model instance.

    Comprehensive schema from model_instances.py with full parameter support.
    """

    provider_id: str = Field(..., description="Provider UUID (must reference an existing registered provider)")
    instance_name: str = Field(..., description="Human-readable instance name for display and reference")
    model_id: str = Field(
        ..., description="Model identifier used by the provider (e.g., 'gpt-4o', 'llama3.2:3b-instruct-q4_K_M')"
    )
    model_uri: str | None = Field(
        None, description="Optional model-specific URI (e.g., Azure deployment URL, local file path)"
    )
    tenant_id: str | None = Field(
        None, description="Tenant scope for multi-tenancy (null = global instance accessible to all tenants)"
    )
    parameters: dict[str, Any] | None = Field(
        None,
        description="Model-specific parameters (temperature, max_tokens, top_p, etc.). Known fields are validated; additional properties allowed for provider-specific settings.",
    )
    context_window: int | None = Field(
        None, ge=1024, description="Maximum context window size in tokens (null = use provider default)"
    )
    modalities: list[str] | None = Field(
        None,
        description='Supported modalities: "text" (chat/completion), "vision" (image input), "audio" (speech), "tool" (function calling)',
    )
    description: str | None = Field(None, description="Optional human-readable description of this instance")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "summary": "GPT-4o (OpenAI)",
                    "description": "Latest GPT-4 Omni model with multimodal capabilities",
                    "value": {
                        "provider_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "instance_name": "gpt-4o-production",
                        "model_id": "gpt-4o",
                        "tenant_id": None,
                        "parameters": {
                            "temperature": 0.7,
                            "max_tokens": 4096,
                            "top_p": 1.0,
                            "frequency_penalty": 0.0,
                            "presence_penalty": 0.0,
                        },
                        "context_window": 128000,
                        "modalities": ["text", "vision", "audio"],
                        "description": "GPT-4 Omni - multimodal capabilities for production workloads",
                    },
                },
                {
                    "summary": "Llama 3.2 3B (Ollama)",
                    "description": "Self-hosted local model via Ollama",
                    "value": {
                        "provider_id": "d4e5f6a7-b8c9-0123-def0-234567890123",
                        "instance_name": "ollama-llama3.2-3b",
                        "model_id": "llama3.2:3b-instruct-q4_K_M",
                        "tenant_id": None,
                        "parameters": {"temperature": 0.7, "num_ctx": 8192, "num_predict": 512},
                        "context_window": 8192,
                        "modalities": ["text"],
                        "description": "Local Llama 3.2 3B with 4-bit quantization for fast inference",
                    },
                },
            ]
        }
    }


class LoadInstanceResponse(BaseModel):
    """Response for instance load operation."""

    id: str = Field(..., description="Instance ID (UUID)")
    instance_name: str
    provider_id: str
    model_id: str
    enabled: bool
    loaded: bool
    created_at: str
    etag: str


class ListInstancesResponse(BaseModel):
    """
    Response for list instances.

    Uses standard format {items, total, etag, next_page_token}.
    Maintains backward compatibility via aliases (instances -> items, count -> total).
    """

    items: list[dict[str, Any]] = Field(..., description="List of model instance objects")
    total: int = Field(..., description="Total number of instances")
    etag: str = Field(..., description="ETag for cache validation")
    next_page_token: str | None = Field(None, description="Pagination continuation token")

    # Backward compatibility aliases
    @property
    def instances(self) -> list[dict[str, Any]]:
        """Deprecated: Use 'items' instead."""
        return self.items

    @property
    def count(self) -> int:
        """Deprecated: Use 'total' instead."""
        return self.total

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "items": [{"id": "uuid", "instance_name": "mistral-7b", "enabled": True, "loaded": True}],
                "total": 4,
                "etag": "abc123def456",
                "next_page_token": None,
            }
        }
    )


class InstanceDetail(BaseModel):
    """Detailed instance information."""

    id: str = Field(..., description="Instance UUID")
    instance_name: str = Field(..., description="Human-readable instance name")
    provider_id: str = Field(..., description="Provider UUID")
    model_id: str = Field(..., description="Model identifier")
    model_uri: str | None = Field(None, description="Model-specific URI")
    tenant_id: str | None = Field(None, description="Tenant scope (null=global)")
    parameters: dict[str, Any] | None = Field(None, description="Model parameters")
    context_window: int | None = Field(None, description="Context window size in tokens")
    modalities: list[str] | None = Field(None, description="Supported modalities")
    description: str | None = Field(None, description="Instance description")
    enabled: bool = Field(..., description="Whether instance is enabled")
    loaded: bool = Field(..., description="Whether instance is currently loaded")
    created_at: str = Field(..., description="Creation timestamp (ISO 8601)")
    updated_at: str | None = Field(None, description="Last update timestamp (ISO 8601)")
    created_by: str | None = Field(None, description="Actor who created the instance")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "instance_name": "gpt-4o-production",
                "provider_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
                "model_id": "gpt-4o",
                "model_uri": None,
                "tenant_id": None,
                "parameters": {"temperature": 0.7, "max_tokens": 4096},
                "context_window": 128000,
                "modalities": ["text", "vision", "audio"],
                "description": "GPT-4 Omni - multimodal capabilities for production workloads",
                "enabled": True,
                "loaded": True,
                "created_at": "2025-01-15T10:30:00Z",
                "updated_at": "2025-01-15T10:30:00Z",
                "created_by": "admin@example.com",
            }
        }
    }


# ---------------- Default Model Selection ----------------
class GetDefaultResponse(BaseModel):
    """Response for get default model."""

    chat: dict[str, Any] = Field(..., description="Default chat model info")
    etag: str


class SetDefaultRequest(BaseModel):
    """
    Request to set default model.

    **IMPORTANT:** Send the raw JSON from the example. Do NOT wrap in summary/description/value.

    Preferred format: {"chat": {"instance_id": "<uuid>"}}
    Legacy formats supported for backward compatibility.
    """

    chat: dict[str, str] | None = Field(
        None,
        description='Chat model selection (preferred: {"instance_id": "<uuid>"} or legacy: {"name": "<instance-name>"})',
    )
    name: str | None = Field(None, description="DEPRECATED: Top-level instance name (use chat.instance_id instead)")
    instance_id: str | None = Field(
        None, description="DEPRECATED: Top-level instance ID (use chat.instance_id instead)"
    )

    model_config = {
        "extra": "forbid",  # Reject unknown fields like summary/description/value
    }


class SetDefaultResponse(BaseModel):
    """Response for set default operation."""

    ok: bool = True
    message: str = "Default model updated successfully"
    instance_id: str
    instance_name: str


# ---------------- Model Testing ----------------
class TestRequest(BaseModel):
    """
    Model test request.

    Used for health checks and quick diagnostic tests against a model instance.
    """

    model: str | None = Field(None, description="Optional model override to address the test to")
    prompt: str | None = Field(
        None,
        description="Prompt text used for the quick diagnostic test (alternative to messages)",
        examples=[
            "Explain quantum computing in one sentence.",
            "What is the capital of France?",
            "Write a haiku about programming.",
        ],
    )
    messages: list[dict[str, Any]] | None = Field(
        None, description="Pre-formatted OpenAI-style chat messages (alternative to prompt)"
    )
    temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="Sampling temperature for the test (default 0.0 for deterministic output)",
    )
    max_tokens: int = Field(
        default=32, ge=1, le=4096, description="Maximum tokens to synthesize for the test (default 32 for fast tests)"
    )
    stop: list[str] | None = Field(None, description="Optional stop sequences (smart defaults applied if None)")
    one_sentence: bool = Field(
        default=True, description="Enforce single-sentence response via system prompt and truncation (default True)"
    )
    no_system: bool = Field(default=False, description="Skip system message injection (default False)")
    format_hint: str | None = Field(
        None,
        description="Optional format hint for special cases (e.g., 'poem', 'list')",
        examples=["poem", "list", "json"],
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Optional metadata forwarded to the adapter")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "prompt": "Explain quantum computing in one sentence.",
                    "temperature": 0.0,
                    "max_tokens": 32,
                    "one_sentence": True,
                },
                {
                    "prompt": "What is the capital of France?",
                    "temperature": 0.0,
                    "max_tokens": 32,
                    "one_sentence": True,
                },
                {
                    "prompt": "Write a haiku about programming.",
                    "temperature": 0.0,
                    "max_tokens": 24,
                    "format_hint": "poem",
                    "one_sentence": False,
                },
            ]
        }
    }


class TestInstanceRequest(BaseModel):
    """Request to test instance with prompt (alternative to TestRequest)."""

    prompt: str | None = Field(None, description="Test prompt to send to the model (converted to user message)")
    messages: list[dict[str, str]] | None = Field(
        None, description="Pre-formatted chat messages (alternative to prompt)"
    )
    temperature: float | None = Field(
        0.0, ge=0.0, le=2.0, description="Sampling temperature (0.0 = deterministic, default 0.0)"
    )
    max_tokens: int | None = Field(
        32, ge=1, le=8000, description="Maximum tokens to generate (default 32 for concise tests)"
    )
    stop: list[str] | None = Field(
        None, description="Stop sequences (if None, uses smart defaults based on one_sentence)"
    )
    one_sentence: bool = Field(
        True, description='Enforce single-sentence responses (adds stop=["\\n"] and system instruction)'
    )
    no_system: bool = Field(False, description="Skip system message injection (advanced use only)")
    format_hint: str | None = Field(None, description="Format hint for output (e.g., 'poem', 'list')")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "summary": "Factual deterministic",
                    "description": "Deterministic test with temperature=0.0 for consistent results",
                    "value": {
                        "prompt": "What is the capital of France?",
                        "temperature": 0.0,
                        "max_tokens": 32,
                        "one_sentence": True,
                    },
                },
                {
                    "summary": "Short answer",
                    "description": "Quick test with minimal tokens for concise response",
                    "value": {
                        "prompt": "Explain quantum computing in one sentence.",
                        "temperature": 0.0,
                        "max_tokens": 64,
                        "one_sentence": True,
                    },
                },
            ]
        }
    }


class Usage(BaseModel):
    """Token usage metrics."""

    prompt_tokens: int = Field(0, description="Number of tokens consumed by the prompt")
    completion_tokens: int = Field(0, description="Number of tokens consumed by the completion")
    total_tokens: int = Field(0, description="Sum of prompt and completion tokens")


class TestResponse(BaseModel):
    """Response from model test operation."""

    model: str = Field(..., description="Model used to produce the response")
    output: str = Field(..., description="Generated output text")
    usage: Usage = Field(default_factory=Usage, description="Token usage metrics when available from adapter")
    trace_id: str = Field(..., description="Provenance trace identifier")
    event_id: str = Field(..., description="Provenance event identifier")
    provider: str | None = Field(None, description="Provider used for the test request")
    provider_base_url: str | None = Field(None, description="Provider base URL for debugging connectivity issues")
    latency_ms: float | None = Field(None, description="Request latency in milliseconds")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Actual parameters used for the test")

    model_config = {
        "json_schema_extra": {
            "example": {
                "model": "llama3.2:3b-instruct",
                "output": "Quantum computing harnesses quantum-mechanical phenomena to solve certain problems faster than classical computers.",
                "usage": {"prompt_tokens": 22, "completion_tokens": 16, "total_tokens": 38},
                "trace_id": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
                "event_id": "evt_7f8e9d0a1b2c3d4e5f6",
                "provider": "ollama-local",
                "provider_base_url": "http://ollama:11434",
                "latency_ms": 1842.5,
                "parameters": {"temperature": 0.0, "max_tokens": 32, "one_sentence": True},
            }
        }
    }


class TestInstanceResponse(BaseModel):
    """Response for instance test."""

    model: str
    output: str
    usage: dict[str, Any] | None = None
    trace_id: str
    event_id: str
    provider: str | None = Field(None, description="Provider used for the request")
    provider_base_url: str | None = Field(None, description="Provider base URL for debugging")
    latency_ms: float | None = Field(None, description="Request latency in milliseconds")
    parameters: dict[str, Any] | None = Field(None, description="Actual parameters used for the test")

    model_config = {
        "json_schema_extra": {
            "example": {
                "model": "llama3.2:3b-instruct",
                "output": "Quantum computing uses quantum-mechanical phenomena to perform calculations exponentially faster than classical computers.",
                "usage": {"prompt_tokens": 15, "completion_tokens": 17, "total_tokens": 32},
                "trace_id": "trace-a1b2c3d4e5f6g7h8",
                "event_id": "event-7f8e9d0a1b2c3d4e",
                "provider": "ollama-local",
                "provider_base_url": "http://ollama:11434",
                "latency_ms": 1234.5,
                "parameters": {"temperature": 0.0, "max_tokens": 32},
            }
        }
    }


# ---------------- Completions ----------------
class CompletionRequest(BaseModel):
    """Request for text completion."""

    prompt: str = Field(..., description="Prompt text to complete")
    model: str | None = Field(default=None, description="Model name; uses default if omitted")
    temperature: float = Field(default=0.2, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: int = Field(default=256, ge=1, le=8192, description="Maximum number of tokens to generate")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Optional metadata passed to the adapter")


class CompletionResponse(BaseModel):
    """Response from completion operation."""

    model: str = Field(..., description="Model that produced the completion")
    output: str = Field(..., description="Generated completion text")
    usage: Usage = Field(default_factory=Usage, description="Token usage metrics when available")
    latency_ms: int = Field(..., description="Observed latency in milliseconds")
    trace_id: str = Field(..., description="Provenance trace identifier")
    event_id: str = Field(..., description="Provenance event identifier")


# ---------------- Embeddings ----------------
class EmbeddingRequest(BaseModel):
    """Request to create embeddings."""

    input: str = Field(..., description="Text to embed")
    model: str | None = Field(None, description="Optional embedding model to use")


class EmbeddingVector(BaseModel):
    """Single embedding vector."""

    index: int = Field(0, description="Index of the embedding in the response")
    embedding: list[float] = Field(..., description="Embedding vector values")
    model: str = Field(..., description="Model used to produce the embedding")


class EmbeddingResponse(BaseModel):
    """Response from embeddings operation."""

    data: list[EmbeddingVector] = Field(..., description="Embedding vectors returned by the provider")
    latency_ms: int = Field(..., description="Observed latency in milliseconds")
    trace_id: str = Field(..., description="Provenance trace identifier")
    event_id: str = Field(..., description="Provenance event identifier")
    usage: Usage | None = Field(default=None, description="Token usage when provided by the upstream provider")


# ---------------- Chat ----------------
class ChatRequest(BaseModel):
    """Request for chat completions."""

    messages: list[dict[str, Any]] = Field(..., description="Ordered list of chat messages (role/content pairs)")
    model: str | None = Field(None, description="Optional model to use for chat completions")


# ---------------- Admin Actions ----------------
class ActionResponse(BaseModel):
    """Generic action response for admin operations."""

    ok: bool = Field(..., description="Whether the action completed successfully")
    message: str = Field(..., description="Human-friendly message describing the outcome")
    details: dict[str, Any] = Field(default_factory=dict, description="Optional adapter-specific details")
    trace_id: str = Field(..., description="Provenance trace identifier")
    event_id: str = Field(..., description="Provenance event identifier")


class PatchDefaultsBody(BaseModel):
    """Request body for PATCH /defaults (legacy endpoint)."""

    chat: dict[str, str] | None = None
    name: str | None = None


class UnregisterLLMRequest(BaseModel):
    """Request to unregister LLM instance."""

    instance_id: str = Field(..., description="Instance UUID to unregister")


# ---------------- Type Exports ----------------
__all__ = [
    "ModelInfo",
    "InstanceCreateRequest",
    "LoadInstanceRequest",
    "LoadInstanceResponse",
    "ListInstancesResponse",
    "InstanceDetail",
    "GetDefaultResponse",
    "SetDefaultRequest",
    "SetDefaultResponse",
    "TestRequest",
    "TestInstanceRequest",
    "Usage",
    "TestResponse",
    "TestInstanceResponse",
    "CompletionRequest",
    "CompletionResponse",
    "EmbeddingRequest",
    "EmbeddingVector",
    "EmbeddingResponse",
    "ChatRequest",
    "ActionResponse",
    "PatchDefaultsBody",
    "UnregisterLLMRequest",
    "Modality",
]
