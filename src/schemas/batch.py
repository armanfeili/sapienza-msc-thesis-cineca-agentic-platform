"""
Pydantic schemas for Batch Operations API.

Defines canonical request/response models for bulk operations.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class BatchOperation(BaseModel):
    """Single operation in a batch request."""

    operation: str = Field(..., description="Operation type: create, update, delete")
    resourceType: str = Field(..., description="Resource type: model, tenant, tool, agent")
    resourceId: str | None = Field(None, description="Resource ID (for update/delete)")
    data: dict[str, Any] | None = Field(None, description="Resource data (for create/update)")


class BatchRequest(BaseModel):
    """Batch operation request."""

    operations: list[BatchOperation] = Field(..., description="List of operations to perform")
    continueOnError: bool = Field(default=False, description="Continue processing if an operation fails")
    atomic: bool = Field(default=False, description="Rollback all operations if any fails (not yet supported)")


class BatchOperationResult(BaseModel):
    """Result of a single operation."""

    operation: str = Field(..., description="Operation type that was attempted")
    resourceType: str = Field(..., description="Resource type that was targeted")
    resourceId: str | None = Field(None, description="Resource ID (if applicable)")
    success: bool = Field(..., description="Whether the operation succeeded")
    statusCode: int = Field(..., description="HTTP-style status code")
    message: str | None = Field(None, description="Human-readable result message")
    data: dict[str, Any] | None = Field(None, description="Result data (for successful operations)")
    error: str | None = Field(None, description="Error message (for failed operations)")


class BatchResponse(BaseModel):
    """Batch operation response."""

    totalOperations: int = Field(..., description="Total number of operations in the batch")
    successCount: int = Field(..., description="Number of successful operations")
    failureCount: int = Field(..., description="Number of failed operations")
    results: list[BatchOperationResult] = Field(..., description="Results for each operation")
    errors: list[str] = Field(default_factory=list, description="List of global errors (if any)")
