"""
Pydantic models for admin process management API responses.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProcessInfo(BaseModel):
    """Information about a single built-in process."""

    id: str = Field(..., description="Unique process identifier")
    process_id: str = Field(..., description="Stable process identifier across restarts")
    artifact: str = Field(..., description="Artifact name (e.g., 'llama3-8b', 'whisper-large')")
    pid: int | None = Field(None, description="Operating system process ID")
    port: int | None = Field(None, description="Listening port if applicable")
    status: str = Field(..., description="Process status: 'running', 'starting', 'stopping', 'exited'")
    ts: datetime = Field(..., description="Last update timestamp (ISO 8601)")
    tenant_id: str | None = Field(None, description="Tenant identifier if applicable")
    manifest_version: str | None = Field(None, description="Manifest version that started this process")
    host: str | None = Field(None, description="Hostname or pod identifier")
    last_heartbeat: datetime | None = Field(None, description="Last heartbeat timestamp")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "llama3-8b-1234",
                "process_id": "builtin:llama3-8b:abc123",
                "artifact": "llama3-8b",
                "pid": 42789,
                "port": 8080,
                "status": "running",
                "ts": "2025-10-21T10:30:00Z",
                "tenant_id": "tenant-001",
                "manifest_version": "v1.2.3",
                "host": "worker-01",
                "last_heartbeat": "2025-10-21T10:35:00Z",
            }
        }
    )


class ProcessListResponse(BaseModel):
    """Response for GET /admin/processes."""

    processes: list[ProcessInfo] = Field(..., description="List of active and recent processes")
    next_cursor: str | None = Field(None, description="Cursor for pagination; omit if no more results")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "processes": [
                    {
                        "id": "llama3-8b-1234",
                        "process_id": "builtin:llama3-8b:abc123",
                        "artifact": "llama3-8b",
                        "pid": 42789,
                        "port": 8080,
                        "status": "running",
                        "ts": "2025-10-21T10:30:00Z",
                        "tenant_id": None,
                        "manifest_version": "v1.2.3",
                        "host": "localhost",
                        "last_heartbeat": "2025-10-21T10:35:00Z",
                    }
                ],
                "next_cursor": None,
            }
        }
    )


class ManifestActivationRecord(BaseModel):
    """Record of a manifest activation/rollback operation."""

    id: str = Field(..., description="Unique record identifier")
    manifest_name: str = Field(..., description="Name of the manifest")
    version: str = Field(..., description="Manifest version")
    status: str = Field(..., description="Status: 'staged', 'active', 'rolled_back', 'failed'")
    activated_at: datetime = Field(..., description="Activation timestamp (ISO 8601)")
    activated_by: str | None = Field(None, description="User or system identifier")
    notes: str | None = Field(None, description="Optional context or reason")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "manifest_name": "production-builtins",
                "version": "v1.2.3",
                "status": "active",
                "activated_at": "2025-10-21T09:00:00Z",
                "activated_by": "auth0|68c709969225afe265151ed5",
                "notes": "Rolled out new model versions",
            }
        }
    )


class ManifestHistoryResponse(BaseModel):
    """Response for GET /admin/processes/history/manifests."""

    manifests: list[ManifestActivationRecord] = Field(..., description="List of manifest activation records")
    next_cursor: str | None = Field(None, description="Cursor for pagination; omit if no more results")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "manifests": [
                    {
                        "id": "550e8400-e29b-41d4-a716-446655440000",
                        "manifest_name": "production-builtins",
                        "version": "v1.2.3",
                        "status": "active",
                        "activated_at": "2025-10-21T09:00:00Z",
                        "activated_by": "auth0|admin",
                        "notes": None,
                    }
                ],
                "next_cursor": None,
            }
        }
    )


class ProcessEventRecord(BaseModel):
    """Record of a process lifecycle event."""

    id: str = Field(..., description="Unique event identifier")
    process_id: str = Field(..., description="Process identifier")
    artifact: str = Field(..., description="Artifact name")
    pid: int | None = Field(None, description="Operating system process ID")
    port: int | None = Field(None, description="Listening port")
    event: str = Field(..., description="Event type: 'start', 'heartbeat', 'stop', 'exit', 'signal'")
    reason: str | None = Field(None, description="Event reason or context")
    exit_code: int | None = Field(None, description="Exit code for 'exit' events")
    ts: datetime = Field(..., description="Event timestamp (ISO 8601)")
    tenant_id: str | None = Field(None, description="Tenant identifier")
    manifest_version: str | None = Field(None, description="Manifest version")
    host: str | None = Field(None, description="Hostname or pod identifier")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "660e8400-e29b-41d4-a716-446655440000",
                "process_id": "builtin:llama3-8b:abc123",
                "artifact": "llama3-8b",
                "pid": 42789,
                "port": 8080,
                "event": "start",
                "reason": "manifest_activation",
                "exit_code": None,
                "ts": "2025-10-21T10:30:00Z",
                "tenant_id": None,
                "manifest_version": "v1.2.3",
                "host": "localhost",
            }
        }
    )


class ProcessHistoryResponse(BaseModel):
    """Response for GET /admin/processes/history/processes."""

    events: list[ProcessEventRecord] = Field(..., description="List of process lifecycle events")
    next_cursor: str | None = Field(None, description="Cursor for pagination; omit if no more results")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "events": [
                    {
                        "id": "660e8400-e29b-41d4-a716-446655440000",
                        "process_id": "builtin:llama3-8b:abc123",
                        "artifact": "llama3-8b",
                        "pid": 42789,
                        "port": 8080,
                        "event": "start",
                        "reason": "manifest_activation",
                        "exit_code": None,
                        "ts": "2025-10-21T10:30:00Z",
                        "tenant_id": None,
                        "manifest_version": "v1.2.3",
                        "host": "localhost",
                    }
                ],
                "next_cursor": None,
            }
        }
    )


__all__ = [
    "ManifestActivationRecord",
    "ManifestHistoryResponse",
    "ProcessEventRecord",
    "ProcessHistoryResponse",
    "ProcessInfo",
    "ProcessListResponse",
]
