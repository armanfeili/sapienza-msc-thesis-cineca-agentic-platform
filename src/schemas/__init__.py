"""
Pydantic schemas package for Cineca Agentic Platform API.

This package contains all canonical Pydantic models (DTOs) used across the API.
All request/response models must be defined here, not in routers.

Organization:
- agents.py: Agent session, step, and run schemas
- jobs.py: Background job schemas (PostgreSQL-backed)
- providers.py: LLM provider management schemas
- tenants.py: Tenant management schemas
- models.py: Model instance and LLM-related schemas
- tools.py: MCP tool schemas
- admin.py: Admin-specific schemas
- batch.py: Batch operation schemas
- export_import.py: Export/import schemas
- manifests.py: Manifest management schemas
- auth.py: Authentication/authorization schemas

Architectural Rule:
**ALL Pydantic request/response models MUST live in schemas/*.py**
**Routers MUST only import these models, never define new Pydantic models**

If a router needs a variation, create it in schemas/ and import it.
Example: AgentRead, AgentReadPublic, AgentCreate, AgentUpdate all belong in schemas/agents.py
"""

__all__ = [
    # Re-export commonly used schemas for convenience
    # Agents
    "CreateSessionRequest",
    "SessionResponse",
    "SessionListItem",
    "SessionListResponse",
    "CreateStepRequest",
    "StepResponse",
    "StepListResponse",
    "CreateRunRequest",
    "RunResponse",
    "OrchestrationStepInput",
    "OrchestrationStepOutput",
    "TodoItem",
    "LLMCallMetrics",
    "ToolCallMetrics",
    "ExecutionMetrics",
    "ProblemDetail",
    # Jobs
    "JobCreateRequest",
    "JobResponse",
    "JobListResponse",
    "JobEventResponse",
    # Providers
    "Provider",
    "ProviderListResponse",
    "RegisterProviderRequest",
    "UpdateProviderRequest",
    "SetDefaultProviderRequest",
    "ActionResponse",
    "GetMainProviderResponse",
    "ProviderHealth",
    "ProviderType",
    "ProviderConfig",
    "Timeouts",
    "TLSConfig",
    "Paths",
    "RequestTemplates",
    "ResponseExtract",
    "AuthConfig",
    "ProblemDetails",
    "ValidationErrorDetail",
    "ValidationProblemDetails",
    # Tenants
    "Tenant",
    "TenantListResponse",
    "CreateTenantRequest",
    "UpdateTenantRequest",
]

# Import schemas for re-export
from src.schemas.agents import (
    CreateRunRequest,
    CreateSessionRequest,
    CreateStepRequest,
    ExecutionMetrics,
    LLMCallMetrics,
    OrchestrationStepInput,
    OrchestrationStepOutput,
    ProblemDetail,
    RunResponse,
    SessionListItem,
    SessionListResponse,
    SessionResponse,
    StepListResponse,
    StepResponse,
    TodoItem,
    ToolCallMetrics,
)
from src.schemas.jobs import (
    JobCreateRequest,
    JobEventResponse,
    JobListResponse,
    JobResponse,
)
from src.schemas.providers import (
    ActionResponse,
    AuthConfig,
    GetMainProviderResponse,
    Paths,
    ProblemDetails,
    Provider,
    ProviderConfig,
    ProviderHealth,
    ProviderListResponse,
    ProviderType,
    RegisterProviderRequest,
    RequestTemplates,
    ResponseExtract,
    SetDefaultProviderRequest,
    TLSConfig,
    Timeouts,
    UpdateProviderRequest,
    ValidationErrorDetail,
    ValidationProblemDetails,
)
from src.schemas.tenants import (
    CreateTenantRequest,
    Tenant,
    TenantListResponse,
    UpdateTenantRequest,
)
