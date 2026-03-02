"""
Pydantic schemas for Tenant management API.

Defines canonical request/response models for tenant CRUD operations,
including proper validation, pagination, and RFC 7807 error responses.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# ---------- Core Tenant Models ----------


class Tenant(BaseModel):
    """Canonical Tenant schema used for GET/LIST responses."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Unique tenant identifier (server-generated)")
    name: str = Field(..., description="Human-friendly tenant name")
    admin_email: str = Field(..., description="Contact email for tenant administrator (RFC 5322)")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Arbitrary tenant metadata (permissive, preserved on readback)"
    )
    created_at: str = Field(..., description="Creation timestamp (ISO 8601)")
    updated_at: str = Field(..., description="Last update timestamp (ISO 8601)")


class TenantListResponse(BaseModel):
    """Paginated list of tenants."""

    items: list[Tenant] = Field(default_factory=list, description="List of tenants")
    next_page_token: str | None = Field(default=None, description="Token for next page (if available)")
    total: int | None = Field(default=None, description="Total count of tenants (optional)")


# ---------- Request Models ----------


class CreateTenantRequest(BaseModel):
    """
    Request to create a new tenant.

    **Required fields**: `name`, `admin_email`
    **Optional fields**: `metadata` (defaults to empty dict)
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "name": "ACME Corporation",
                    "admin_email": "admin@example.com",
                    "metadata": {
                        "region": "us-east-1",
                        "tier": "premium",
                        "contact": {"slack": "#acme-admins", "phone": "+1-555-0100"},
                        "features": ["a", "b", "c"],
                    },
                },
                {"name": "ACME", "admin_email": "admin@example.com"},
            ]
        },
    )

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Display name for the tenant",
        examples=["ACME Corporation", "Beta Test Tenant"],
    )
    admin_email: EmailStr = Field(
        ...,
        description="Contact email for tenant administrator (must be valid RFC 5322 email)",
        examples=["admin@example.com", "contact@example.com"],
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional tenant metadata (arbitrary keys supported)",
        examples=[{"region": "us-east-1", "tier": "premium"}, {}],
    )

    @field_validator("metadata")
    @classmethod
    def validate_metadata_is_dict(cls, value: Any) -> dict[str, Any]:
        """Ensure metadata is a dictionary."""
        if not isinstance(value, dict):
            raise ValueError("metadata must be a dictionary")
        return value


class UpdateTenantRequest(BaseModel):
    """Request to update an existing tenant (partial update)."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, min_length=1, max_length=255, description="Updated display name")
    admin_email: EmailStr | None = Field(
        None, description="Updated admin contact email (must be valid RFC 5322 email)"
    )
    metadata: dict[str, Any] | None = Field(
        None, description="Metadata updates (deep-merged with existing metadata)"
    )


# ---------- Response Models ----------


class ActionResponse(BaseModel):
    """Generic action response with success/failure details."""

    model_config = ConfigDict(extra="allow")

    ok: bool = Field(..., description="Whether the operation succeeded")
    message: str = Field(..., description="Human-readable result message")
    details: dict[str, Any] | None = Field(default=None, description="Additional details")
    trace_id: str | None = Field(default=None, description="Distributed trace ID")
    event_id: str | None = Field(default=None, description="Event/provenance ID")


# ---------- Error Models (RFC 7807) ----------


class ProblemDetails(BaseModel):
    """RFC 7807 Problem Details for HTTP APIs."""

    model_config = ConfigDict(extra="allow")

    type: str = Field(default="about:blank", description="Problem type URI")
    title: str = Field(..., description="Short, human-readable summary (must match HTTP status)")
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
