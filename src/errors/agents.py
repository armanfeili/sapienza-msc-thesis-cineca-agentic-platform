"""Standardized error responses for Agents API using RFC7807 ProblemDetail."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from src.schemas.agents import ProblemDetail


# Error codes for structured error tracking
class AgentErrorCode:
    """Standardized error codes for agent operations."""

    # Resource errors (404)
    SESSION_NOT_FOUND = "session_not_found"
    STEP_NOT_FOUND = "step_not_found"
    RUN_NOT_FOUND = "run_not_found"

    # State errors (400)
    SESSION_NOT_ACTIVE = "session_not_active"
    SESSION_ALREADY_EXISTS = "session_already_exists"
    INVALID_CURSOR = "invalid_cursor"
    INVALID_REQUEST = "invalid_request"

    # Conflict errors (409)
    DUPLICATE_SESSION = "duplicate_session"
    DUPLICATE_IDEMPOTENCY_KEY = "duplicate_idempotency_key"

    # Server errors (500)
    DATABASE_ERROR = "database_error"
    REDIS_ERROR = "redis_error"
    INTERNAL_ERROR = "internal_error"


def create_problem_detail(
    status_code: int,
    title: str,
    detail: str,
    error_code: str | None = None,
    instance: str | None = None,
    extensions: dict[str, Any] | None = None,
) -> ProblemDetail:
    """
    Create RFC7807 ProblemDetail with consistent structure.

    Args:
        status_code: HTTP status code
        title: Short, human-readable summary
        detail: Human-readable explanation specific to this occurrence
        error_code: Machine-readable error code (e.g., "session_not_found")
        instance: URI reference identifying specific occurrence
        extensions: Additional error-specific data

    Returns:
        ProblemDetail instance
    """
    # Map status codes to type URIs
    type_map = {
        400: "https://httpstatuses.com/400",
        404: "https://httpstatuses.com/404",
        409: "https://httpstatuses.com/409",
        429: "https://httpstatuses.com/429",
        500: "https://httpstatuses.com/500",
    }

    ext = extensions or {}
    if error_code:
        ext["error_code"] = error_code

    return ProblemDetail(
        type=type_map.get(status_code, f"https://httpstatuses.com/{status_code}"),
        title=title,
        status=status_code,
        detail=detail,
        instance=instance,
        extensions=ext if ext else None,
    )


def raise_problem(
    status_code: int,
    title: str,
    detail: str,
    error_code: str | None = None,
    instance: str | None = None,
    extensions: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> None:
    """
    Raise HTTPException with RFC7807 ProblemDetail.

    Args:
        status_code: HTTP status code
        title: Short, human-readable summary
        detail: Human-readable explanation
        error_code: Machine-readable error code
        instance: URI reference identifying specific occurrence
        extensions: Additional error-specific data
        headers: Optional HTTP headers to include

    Raises:
        HTTPException with ProblemDetail as detail
    """
    problem = create_problem_detail(
        status_code=status_code,
        title=title,
        detail=detail,
        error_code=error_code,
        instance=instance,
        extensions=extensions,
    )

    raise HTTPException(
        status_code=status_code,
        detail=problem.model_dump(mode="json", exclude_none=True),
        headers=headers,
    )


# Convenience functions for common errors


def session_not_found(session_id: str, instance: str | None = None) -> None:
    """Raise 404 for session not found."""
    raise_problem(
        status_code=status.HTTP_404_NOT_FOUND,
        title="Session Not Found",
        detail=f"Agent session '{session_id}' does not exist or you don't have access to it.",
        error_code=AgentErrorCode.SESSION_NOT_FOUND,
        instance=instance,
        extensions={"session_id": session_id},
    )


def step_not_found(step_id: str, session_id: str | None = None, instance: str | None = None) -> None:
    """Raise 404 for step not found."""
    ext = {"step_id": step_id}
    if session_id:
        ext["session_id"] = session_id

    raise_problem(
        status_code=status.HTTP_404_NOT_FOUND,
        title="Step Not Found",
        detail=f"Agent step '{step_id}' does not exist.",
        error_code=AgentErrorCode.STEP_NOT_FOUND,
        instance=instance,
        extensions=ext,
    )


def run_not_found(run_id: str, instance: str | None = None) -> None:
    """Raise 404 for run not found."""
    raise_problem(
        status_code=status.HTTP_404_NOT_FOUND,
        title="Run Not Found",
        detail=f"Agent run '{run_id}' does not exist or you don't have access to it.",
        error_code=AgentErrorCode.RUN_NOT_FOUND,
        instance=instance,
        extensions={"run_id": run_id},
    )


def session_not_active(session_id: str, current_status: str, instance: str | None = None) -> None:
    """Raise 400 for session not in active state."""
    raise_problem(
        status_code=status.HTTP_400_BAD_REQUEST,
        title="Session Not Active",
        detail=f"Session '{session_id}' is not active (current status: {current_status}). Only active sessions can accept new steps.",
        error_code=AgentErrorCode.SESSION_NOT_ACTIVE,
        instance=instance,
        extensions={
            "session_id": session_id,
            "current_status": current_status,
            "expected_status": "active",
        },
    )


def invalid_cursor(cursor: str, reason: str | None = None, instance: str | None = None) -> None:
    """Raise 400 for invalid pagination cursor."""
    detail = f"Invalid pagination cursor: '{cursor}'"
    if reason:
        detail += f". {reason}"

    raise_problem(
        status_code=status.HTTP_400_BAD_REQUEST,
        title="Invalid Cursor",
        detail=detail,
        error_code=AgentErrorCode.INVALID_CURSOR,
        instance=instance,
        extensions={"cursor": cursor},
    )


def duplicate_session(session_id: str, instance: str | None = None) -> None:
    """Raise 409 for duplicate session ID."""
    raise_problem(
        status_code=status.HTTP_409_CONFLICT,
        title="Duplicate Session",
        detail=f"Session '{session_id}' already exists. Use a different session_id or omit it for auto-generation.",
        error_code=AgentErrorCode.DUPLICATE_SESSION,
        instance=instance,
        extensions={"session_id": session_id},
    )


def database_error(operation: str, error: str, instance: str | None = None) -> None:
    """Raise 500 for database errors."""
    raise_problem(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        title="Database Error",
        detail=f"Failed to {operation}: {error}",
        error_code=AgentErrorCode.DATABASE_ERROR,
        instance=instance,
        extensions={"operation": operation},
    )


def internal_error(detail: str, instance: str | None = None, extensions: dict[str, Any] | None = None) -> None:
    """Raise 500 for internal server errors."""
    raise_problem(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        title="Internal Server Error",
        detail=detail,
        error_code=AgentErrorCode.INTERNAL_ERROR,
        instance=instance,
        extensions=extensions,
    )
