"""
Pydantic schemas for Tools API.

Defines canonical request/response models for MCP tool management and invocation.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ToolInfo(BaseModel):
    """Information about a registered or discovered tool."""

    id: str = Field(..., description='Unique tool identifier with version (e.g., "graph.query@1")')
    name: str = Field(..., description='Short dotted name (e.g., "graph.query")')
    module: str | None = Field(None, description="Python import path (admin only; redacted for non-admin)")
    entrypoint: str | None = Field(None, description="Callable used, if detected")
    description: str | None = Field(None, description="Short human-friendly description of the tool")
    input_schema: dict[str, Any] | None = Field(
        None, description="JSON Schema for invocation input (never null for invokable)"
    )
    scopes: list[str] = Field(
        default_factory=list, description="Permissions required to invoke (e.g., ['tools:basic'])"
    )
    capabilities: list[str] = Field(
        default_factory=list, description="Tool capabilities (e.g., ['reads_db', 'writes_db'])"
    )
    namespace: bool = Field(default=False, description="True when this record represents a non-invokable namespace")
    invokable: bool = Field(default=False, description="True when the tool can be invoked via entrypoint")
    long_running: bool = Field(default=False, description="True if tool is expected to run long (async/job)")


class ToolsListResponse(BaseModel):
    """Paginated list of available tools."""

    items: list[ToolInfo] = Field(default_factory=list, description="List of tools")
    next_page_token: str | None = Field(None, description="Token for next page (if available)")
    total: int | None = Field(default=None, description="Total items available (best-effort)")
    has_more: bool | None = Field(default=None, description="Whether more pages are available")


class ToolInvokeRequest(BaseModel):
    """Request to invoke a tool."""

    args: dict[str, Any] = Field(default_factory=dict, description="Keyword arguments passed to the tool")
    timeout_seconds: int | None = Field(
        default=None,
        ge=1,
        le=3600,
        description="Optional execution timeout in seconds (1-3600)",
    )


class ToolInvokeResponse(BaseModel):
    """Response from tool invocation."""

    name: str = Field(..., description="Tool name invoked")
    ok: bool = Field(..., description="Whether the invocation completed successfully")
    result: Any = Field(None, description="Tool-specific result payload")
    error: str | None = Field(None, description="Error message when invocation failed")
    duration_ms: int = Field(..., description="Observed duration of the invocation in milliseconds")
    trace_id: str = Field(..., description="Provenance trace identifier")
    event_id: str = Field(..., description="Provenance event identifier")
