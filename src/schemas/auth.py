"""
Pydantic schemas for Authentication/Authorization.

Defines canonical models for user identity and permissions.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class UserInfo(BaseModel):
    """User identity and permission information extracted from JWT."""

    sub: str | None = Field(None, description="Subject (stable principal identifier)")
    username: str | None = Field(None, description="Deprecated legacy username (unused for auth)")
    tenant_id: str | None = Field(None, description="Resolved tenant id (from header/middleware)")
    scopes: list[str] = Field(default_factory=list, description="Granted scopes (when enforced elsewhere)")
    roles: list[str] = Field(default_factory=list, description="Roles array from token if present")
    permissions: list[str] = Field(default_factory=list, description="Effective permissions (admin routes only)")
