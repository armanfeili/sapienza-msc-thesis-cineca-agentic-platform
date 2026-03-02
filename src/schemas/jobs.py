"""Pydantic models for jobs API (PostgreSQL-backed)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ============================================================================
# Agent Run Job Payload Schema
# ============================================================================

class AgentRunJobPayload(BaseModel):
    """
    Payload schema for agent.run job type.
    
    This payload defines all the parameters needed to execute an agent run
    asynchronously via the jobs worker.
    """

    # Required fields
    prompt: str = Field(
        ...,
        description="The user's prompt/goal for the agent",
        examples=["What is the capital of France?", "Summarize the dataset"],
    )
    user_id: str = Field(
        ...,
        description="User ID (from JWT subject)",
        examples=["user@example.com", "auth0|12345"],
    )
    tenant_id: str = Field(
        ...,
        description="Tenant identifier",
        examples=["default", "tenant-abc"],
    )

    # Optional fields
    session_id: str | None = Field(
        default=None,
        description="Session UUID for context persistence",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
    )
    run_id: str | None = Field(
        default=None,
        description="Pre-generated run ID (if AgentRun was pre-created)",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
    )
    model: str | None = Field(
        default=None,
        description="Specific model to use (overrides default)",
        examples=["phi3:mini", "gpt-4"],
    )
    manager: str | None = Field(
        default=None,
        description="Manager/planner LLM client name",
        examples=["phi3-mini", "planner"],
    )
    temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=2.0,
        description="Sampling temperature",
    )
    max_steps: int = Field(
        default=8,
        ge=1,
        le=50,
        description="Maximum orchestration steps",
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Arbitrary metadata to persist with the run",
        examples=[{"source": "api", "version": "v1"}],
    )
    trace_id: str | None = Field(
        default=None,
        description="Distributed trace ID for observability",
        examples=["abc123def456"],
    )
    request_id: str | None = Field(
        default=None,
        description="HTTP request ID for correlation",
        examples=["req-12345"],
    )
    
    # Security context (populated by worker from job owner)
    principal: dict[str, Any] | None = Field(
        default=None,
        description="Principal context from JWT (sub, roles, permissions)",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "prompt": "What is the capital of France?",
                    "user_id": "user@example.com",
                    "tenant_id": "default",
                    "session_id": "123e4567-e89b-12d3-a456-426614174000",
                    "temperature": 0.2,
                    "max_steps": 8,
                },
                {
                    "prompt": "Analyze the user activity patterns",
                    "user_id": "admin@example.com",
                    "tenant_id": "tenant-abc",
                    "model": "phi3:mini",
                    "metadata": {"source": "dashboard", "priority": "high"},
                },
            ]
        }
    }


class JobCreateRequest(BaseModel):
    """Request to create a new job."""

    type: str = Field(
        ...,
        description="Job type identifier (e.g., 'agent.run', 'demo')",
        examples=["agent.run", "demo"],
    )
    payload: dict = Field(
        default_factory=dict,
        description="Arbitrary JSON payload for the job",
        examples=[{"duration_ms": 1000}, {"test": "data"}],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"type": "agent.run", "payload": {"agent_id": "abc123"}},
                {"type": "demo", "payload": {"duration_ms": 500}},
            ]
        }
    }


class JobResponse(BaseModel):
    """Job representation in API responses."""

    id: str = Field(
        ...,
        description="Job UUID",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
    )
    type: str = Field(..., description="Job type", examples=["agent.run"])
    status: str = Field(
        ...,
        description="Job status (queued, running, finished, failed, cancelled)",
        examples=["queued", "running", "finished"],
    )
    owner_sub: str = Field(..., alias="owner", description="Job owner (token subject)", examples=["user@example.com"])
    tenant_id: str = Field(..., description="Tenant identifier", examples=["default", "tenant-abc"])
    created_at: str = Field(
        ...,
        description="ISO 8601 creation timestamp",
        examples=["2025-10-12T15:30:00Z"],
    )
    updated_at: str | None = Field(
        None,
        description="ISO 8601 last update timestamp",
        examples=["2025-10-12T15:30:05Z"],
    )
    started_at: str | None = Field(
        None,
        description="ISO 8601 start timestamp (when transitioned to running)",
        examples=["2025-10-12T15:30:01Z"],
    )
    completed_at: str | None = Field(
        None,
        description="ISO 8601 completion timestamp (when reached terminal state)",
        examples=["2025-10-12T15:30:10Z"],
    )
    payload: dict | None = Field(None, description="Job payload (only included if requested)")
    result: dict | None = Field(
        None,
        description="Job result (only available after completion)",
        examples=[{"status": "success", "output": "data"}],
    )
    error: dict | None = Field(None, description="Error details (only if status=failed)")
    priority: int = Field(..., description="Job priority", examples=[0, 10])
    queue_latency_ms: int | None = Field(
        None,
        description="Time from created to started (milliseconds)",
        examples=[1234],
    )
    exec_latency_ms: int | None = Field(
        None,
        description="Time from started to completed (milliseconds)",
        examples=[5678],
    )
    etag: str = Field(
        ...,
        description="Entity tag for conditional requests",
        examples=["abc123def456"],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "123e4567-e89b-12d3-a456-426614174000",
                    "type": "agent.run",
                    "status": "finished",
                    "owner_sub": "user@example.com",
                    "tenant_id": "default",
                    "created_at": "2025-10-12T15:30:00Z",
                    "updated_at": "2025-10-12T15:30:10Z",
                    "started_at": "2025-10-12T15:30:01Z",
                    "completed_at": "2025-10-12T15:30:10Z",
                    "result": {"status": "success"},
                    "priority": 0,
                    "queue_latency_ms": 1000,
                    "exec_latency_ms": 9000,
                    "etag": "abc123",
                }
            ]
        }
    }


class JobListResponse(BaseModel):
    """Paginated list of jobs."""

    items: list[JobResponse] = Field(..., description="Jobs in current page")
    total: int = Field(..., description="Total number of jobs matching filters", examples=[100])
    limit: int = Field(..., description="Page size", examples=[25])
    offset: int = Field(..., description="Pagination offset", examples=[0, 25])
    has_more: bool = Field(
        ...,
        description="Whether more pages are available",
        examples=[True, False],
    )
    next_page_token: str | None = Field(
        None,
        description="Opaque token for next page (use as offset query param)",
        examples=["25", "50"],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "items": [
                        {
                            "id": "123e4567-e89b-12d3-a456-426614174000",
                            "type": "agent.run",
                            "status": "finished",
                            "owner_sub": "user@example.com",
                            "tenant_id": "default",
                            "created_at": "2025-10-12T15:30:00Z",
                            "updated_at": "2025-10-12T15:30:10Z",
                            "priority": 0,
                            "etag": "abc123",
                        }
                    ],
                    "total": 100,
                    "limit": 25,
                    "offset": 0,
                    "has_more": True,
                    "next_page_token": "25",
                }
            ]
        }
    }


class JobEventResponse(BaseModel):
    """Job event representation."""

    seq_id: int = Field(..., description="Event sequence ID", examples=[1, 42])
    job_id: str = Field(..., description="Job UUID", examples=["123e4567-..."])
    event_type: str = Field(
        ...,
        description="Event type (status, log, progress, heartbeat, end)",
        examples=["status", "log", "progress"],
    )
    event_json: dict = Field(
        ...,
        description="Event payload",
        examples=[{"status": "running"}, {"message": "Processing..."}],
    )
    created_at: str = Field(
        ...,
        description="ISO 8601 event timestamp",
        examples=["2025-10-12T15:30:05Z"],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "seq_id": 42,
                    "job_id": "123e4567-e89b-12d3-a456-426614174000",
                    "event_type": "status",
                    "event_json": {"status": "running"},
                    "created_at": "2025-10-12T15:30:05Z",
                }
            ]
        }
    }


# Backward compatibility alias for routers using JobRequest name
JobRequest = JobCreateRequest
