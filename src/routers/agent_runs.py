"""
Agent run endpoint for executing agent tasks.

Endpoints:
- POST /agent-runs - Create and execute an agent run
- GET /agent-runs/{id} - Get run details by ID

Runs are persisted in PostgreSQL and linked to sessions.
"""

from __future__ import annotations

import time
import uuid
import json
import os
from copy import deepcopy
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, Response, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session as DBSession

from db.postgres_control.database import get_db
from db.postgres_control.repositories.agents import (
    AgentRunRepository,
    AgentSessionRepository,
)
from db.postgres_control.repositories import model_instance_repo
from src.errors import agents as agent_errors
from src.logging_setup import get_logger
from src.middleware.idempotency import IdempotencyHandler
from src.middleware.rate_limit import RateLimitHandler, add_rate_limit_headers
from src.provenance import record_provenance
from src.schemas.agents import (
    CreateRunRequest,
    ExecutionMetrics,
    OrchestrationStepInput,
    OrchestrationStepOutput,
    RunResponse,
    TodoItem,
)
from src.utils.principal import principal_identity, serialize_principal
from src.utils.run_output import normalize_run_output
from src.services.orchestrator import RUN_TIMEOUT_SECONDS, STEP_TIMEOUT_SECONDS

# Import metrics
try:
    from src.metrics import agent_metrics
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False
    agent_metrics = None  # type: ignore

log = get_logger(__name__)
from src.schemas.auth import UserInfo
from src.security.jwt import Principal
from src.routers.auth import get_current_user

_TRUTHY_VALUES = {"1", "true", "yes", "on"}


def _coerce_truthy(value: Any) -> bool:
    """Return True when value represents an enabled flag."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in _TRUTHY_VALUES
    if isinstance(value, (int, float)):
        return value != 0
    return False


def classify_llm_error(error_message: str) -> str:
    """
    Classify LLM error type from error message (Task C.10).
    
    Args:
        error_message: Error message from orchestrator/LLM provider
        
    Returns:
        Error type: timeout, context_length, rate_limit, connection, validation, or unknown
    """
    msg_lower = error_message.lower()
    
    if any(keyword in msg_lower for keyword in ["timeout", "timed out", "deadline"]):
        return "timeout"
    elif any(keyword in msg_lower for keyword in ["context length", "token limit", "too long", "maximum context"]):
        return "context_length"
    elif any(keyword in msg_lower for keyword in ["rate limit", "quota", "too many requests"]):
        return "rate_limit"
    elif any(keyword in msg_lower for keyword in ["connection", "network", "unreachable", "refused"]):
        return "connection"
    elif any(keyword in msg_lower for keyword in ["validation", "invalid", "malformed"]):
        return "validation"
    else:
        return "unknown"


def _normalize_error_field(error: Any) -> str | None:
    """
    Normalize error field to string for Pydantic validation (B1).
    
    Ensures OrchestrationStepOutput.error is always string or None,
    not dict or other types that would fail Pydantic validation.
    
    Args:
        error: Error value that may be dict, str, or None
        
    Returns:
        Normalized error as string or None
    """
    if error is None:
        return None
    if isinstance(error, str):
        return error
    if isinstance(error, dict):
        import json
        try:
            return json.dumps(error, ensure_ascii=False, default=str)
        except Exception:
            return str(error)
    return str(error)


def _coerce_error_message(error: Any, fallback: str = "Unknown orchestrator error") -> str:
    """Guarantee a string message when surfacing orchestrator errors."""
    normalized = _normalize_error_field(error)
    return normalized if normalized is not None else fallback

from src.security.perm import require_perms, current_permissions
from src.memgraph.test_mode import get_prompt_hints

router = APIRouter(tags=["agents"])


# Helper to get request ID from context
def get_request_id() -> str | None:
    """Get the current request ID from context."""
    try:
        from src.app import _request_id_ctx

        return _request_id_ctx.get()
    except Exception:
        return None


def add_standard_headers(headers: dict, request_id: str | None = None) -> dict:
    """Add standard headers to response: X-Request-Id, Vary."""
    rid = request_id or get_request_id()
    if rid:
        headers.setdefault("X-Request-Id", rid)
    return headers



def _serialize_run_model(run: Any) -> dict[str, Any]:
    """Extract run fields without mutating the ORM object."""
    if hasattr(run, "to_dict"):
        return deepcopy(run.to_dict())

    # Minimal fallback used by unit tests with simple namespaces
    fields = (
        "run_id",
        "session_id",
        "user_id",
        "tenant_id",
        "model",
        "manager",
        "latency_ms",
        "trace_id",
        "request_id",
        "event_id",
        "status",
        "started_at",
        "finished_at",
        "output",
        "steps",
        "todos",
        "metrics",
        "errors",
        "warnings",
        "degraded",
        "used_fallback",
        "total_llm_calls",
        "llm_call_count",
        "tool_calls",
        "tool_errors",
        "run_metadata",
    )
    data = {}
    for field in fields:
        if hasattr(run, field):
            data[field] = getattr(run, field)
    # Normalize metadata key for API consumers
    if "metadata" not in data:
        data["metadata"] = getattr(run, "run_metadata", None) or {}
    else:
        # Ensure metadata is at least an empty dict
        data["metadata"] = data.get("metadata") or {}
    return data


def _build_run_response(run: Any) -> RunResponse:
    """Normalize ORM output before constructing the public schema."""
    payload = _serialize_run_model(run)
    payload["output"] = normalize_run_output(payload.get("output"))
    return RunResponse(**payload)


def _run_response_to_json(result: RunResponse) -> dict[str, Any]:
    """Render a RunResponse into a JSON-serializable payload."""
    return jsonable_encoder(result, exclude_none=False)


def _prepare_run_response_payload(
    run: Any,
    *,
    blank_runtime_fields: bool = False,
) -> tuple[RunResponse, dict[str, Any]]:
    """Return both the validated model and JSON payload for a run."""
    result = _build_run_response(run)
    if blank_runtime_fields:
        result = result.model_copy(
            update={
                "output": None,
                "steps": None,
                "todos": None,
                "errors": None,
            }
        )
    return result, _run_response_to_json(result)


async def execute_agent_run_background(
    run_id: uuid.UUID,
    prompt: str,
    user_id: str,
    session_id: str,
    tenant_id: str,
    params: dict[str, Any],
    request_id: str | None = None,
):
    """
    Execute orchestrator in background and update run status in database.
    
    This function runs asynchronously in a background task, allowing the
    HTTP endpoint to return immediately with status='queued'.
    
    Args:
        run_id: Agent run UUID
        prompt: User prompt/goal
        user_id: User identifier
        session_id: Session UUID
        tenant_id: Tenant identifier
        params: Orchestration parameters (temperature, max_steps, etc.)
        request_id: Original HTTP request ID for tracing
    """
    log.info(
        "agent_run.background.started",
        run_id=str(run_id),
        user_id=user_id,
        session_id=session_id,
        request_id=request_id,
    )
    
    # Track metrics: increment running counter
    if METRICS_AVAILABLE and agent_metrics:
        agent_metrics.dec_queued(tenant_id=tenant_id)
        agent_metrics.inc_running(tenant_id=tenant_id)
    
    start_ns = time.monotonic_ns()
    
    # Get a new database session for this background task
    from db.postgres_control.database import SessionLocal
    db = SessionLocal()
    
    try:
        # Update status to 'running'
        from datetime import datetime, timezone
        AgentRunRepository.update_status(
            db,
            run_id=run_id,
            status="running",
        )
        db.commit()
        log.info("agent_run.background.running", run_id=str(run_id))
        
        # Execute orchestrator
        steps_data: list[OrchestrationStepInput | OrchestrationStepOutput] = []
        todos_data: list[TodoItem] = []
        errors_list: list[str] = []
        warnings_list: list[str] = []
        output_text: str | None = None
        used_model: str | None = None
        success = False
        error_msg: str | None = None
        metrics_data = {}
        
        # LLM error tracking (Task C.10)
        llm_error_type: str | None = None
        llm_error_message: str | None = None
        llm_error_occurred_at: datetime | None = None

        # Import orchestrator timeout constants and failure types
        import asyncio
        from src.models.failure_types import FailureType, get_failure_message

        try:
            from src.services.orchestrator import get_orchestrator_instance

            # Instantiate orchestrator from environment
            orch = get_orchestrator_instance()
            log.info(
                "agent_run.background.principal_context",
                run_id=str(run_id),
                has_principal=bool(params.get("principal")),
                tenant_id=tenant_id,
            )
            
            # Log building_plan stage
            log.info(
                "agent_run.background.building_plan",
                run_id=str(run_id),
                stage="building_plan",
                elapsed_ms=0,
            )

            # Call orchestrator.run() with timeout to prevent hanging forever
            result = None  # Initialize to None before try block
            try:
                result = await asyncio.wait_for(
                    orch.run(
                        goal=prompt,
                        user_id=user_id,
                        session_id=str(session_id),
                        tenant_id=tenant_id,
                        run_id=str(run_id),
                        params=params,
                    ),
                    timeout=RUN_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                # Calculate elapsed time for timeout log
                elapsed_ms = int((time.monotonic_ns() - start_ns) / 1_000_000)
                
                # Determine timeout stage from orchestrator state if available
                timeout_stage = "unknown"
                llm_attempted = 0
                llm_successful = 0
                
                # Try to extract stage info from orchestrator result if partially available
                if hasattr(orch, '_last_result'):
                    partial_result = orch._last_result
                    timeout_stage = getattr(partial_result, 'current_stage', 'unknown')
                    llm_attempted = getattr(partial_result, 'llm_attempted_calls', 0)
                    llm_successful = getattr(partial_result, 'llm_successful_calls', 0)
                
                error_msg = get_failure_message(
                    FailureType.RUN_TIMEOUT,
                    timeout_seconds=RUN_TIMEOUT_SECONDS
                )
                log.error(
                    "agent_run.background.timeout",
                    run_id=str(run_id),
                    timeout_seconds=RUN_TIMEOUT_SECONDS,
                    failure_type=FailureType.RUN_TIMEOUT.value,
                    timeout_stage=timeout_stage,
                    llm_attempted_calls=llm_attempted,
                    llm_successful_calls=llm_successful,
                    elapsed_ms=elapsed_ms,
                )
                errors_list.append(error_msg)
                
                # Classify as timeout error (Task C.10)
                llm_error_type = "timeout"
                llm_error_message = error_msg
                llm_error_occurred_at = datetime.now(timezone.utc)
                
                # Don't clear steps_data/todos_data - preserve partial results
                success = False
                # Continue to result serialization with partial data

            # Extract results from ServiceResult (only if result is available)
            if result and result.data:
                output_text = str(result.data.get("output", ""))
                used_model = result.data.get("manager") or result.data.get("model")
                success = bool(result.ok)
                if not result.ok:
                    errors_list.append(_coerce_error_message(result.error, "Orchestrator reported failure"))
                
                # Extract metrics from orchestrator result (prefer embedded metrics dict)
                raw_metrics = result.data.get("metrics")
                metrics_source = "embedded" if isinstance(raw_metrics, dict) else "legacy"
                if isinstance(raw_metrics, dict):
                    metrics_data = deepcopy(raw_metrics)
                else:
                    metrics_data = {}

                # Backwards compatibility: overlay legacy top-level fields if present
                llm_metrics = result.data.get("llm_metrics")
                if llm_metrics is not None:
                    metrics_data["llm"] = llm_metrics
                else:
                    metrics_data.setdefault("llm", [])

                tool_metrics = result.data.get("tool_metrics")
                if tool_metrics is not None:
                    metrics_data["tools"] = tool_metrics
                else:
                    metrics_data.setdefault("tools", [])

                # Copy common counter fields when provided explicitly
                counter_fields = [
                    "total_llm_calls",
                    "llm_call_count",
                    "llm_attempted_calls",
                    "llm_successful_calls",
                    "tool_calls",
                    "tool_errors",
                    "model_warmup_ms",
                    "timeout_stage",
                ]
                for field in counter_fields:
                    value = result.data.get(field)
                    if value is not None:
                        metrics_data[field] = value
                
                # Derive tools_executed from tool_calls for consistent semantics
                _tools_executed = int(metrics_data.get("tool_calls", 0))
                
                log.info(
                    "agent_run.background.metrics_extracted",
                    run_id=str(run_id),
                    metrics_source=metrics_source,
                    has_llm_metrics=bool(metrics_data.get("llm")),
                    has_tools=(_tools_executed > 0),  # Derived from actual executions
                    tools_executed=_tools_executed,
                    metrics_data_keys=list(metrics_data.keys()),
                    llm_count=len(metrics_data.get("llm", [])),
                    tool_count=len(metrics_data.get("tools", [])),
                    llm_attempted=metrics_data.get("llm_attempted_calls", 0),
                    llm_successful=metrics_data.get("llm_successful_calls", 0),
                )
                
                # Extract TODOs from orchestration result and convert to typed models
                raw_todos = result.data.get("todos", [])
                for todo in raw_todos:
                    if isinstance(todo, dict):
                        todos_data.append(
                            TodoItem(
                                task=todo.get("task", ""),
                                status=todo.get("status"),
                                expect_evidence=todo.get("expect_evidence", True),
                                evidence=todo.get("evidence") or [],
                                meta=todo.get("meta") if isinstance(todo.get("meta"), dict) else {},
                                requires_llm_planning=bool(todo.get("requires_llm_planning", True)),
                                nested_steps=todo.get("nested_steps") or [],
                                fallback_mode=bool(todo.get("fallback_mode", False)),
                            )
                        )
                    elif isinstance(todo, str):
                        todos_data.append(TodoItem(task=todo))

                # Convert steps from orchestration result to typed models
                orchestration_steps = result.data.get("steps", [])
                for step in orchestration_steps:
                    started_at = step.get("started_at")
                    finished_at = step.get("finished_at")
                    latency_ms = step.get("latency_ms")
                    
                    steps_data.append(
                        OrchestrationStepInput(
                            step_id=str(step.get("id")),
                            action=str(step.get("action")),
                            input=step.get("input"),
                            started_at=started_at,
                            finished_at=finished_at,
                            latency_ms=latency_ms,
                        )
                    )

                # Add outputs if available as typed models
                outputs = result.data.get("outputs", [])
                for output in outputs:
                    started_at = output.get("started_at")
                    finished_at = output.get("finished_at")
                    latency_ms = output.get("latency_ms")
                    
                    # B1: Normalize error field to string for Pydantic validation
                    error_value = output.get("error")
                    normalized_error = _normalize_error_field(error_value)
                    
                    steps_data.append(
                        OrchestrationStepOutput(
                            step_id=str(output.get("step_id")),
                            output=output.get("output"),
                            error=normalized_error,
                            started_at=started_at,
                            finished_at=finished_at,
                            latency_ms=latency_ms,
                        )
                    )

                # Collect error messages from orchestration
                if result.data.get("errors"):
                    orchestrator_errors = result.data.get("errors") or []
                    errors_list.extend(
                        _coerce_error_message(err) for err in orchestrator_errors
                    )
                
                # Collect warnings from orchestration
                if result.data.get("warnings"):
                    warnings_list.extend(result.data.get("warnings"))

                # Extract LLM error metadata from metrics when available
                failed_llms = []
                if metrics_data.get("llm"):
                    failed_llms = [m for m in metrics_data.get("llm", []) if m.get("success") is False]
                if failed_llms:
                    first_fail = failed_llms[0]
                    llm_error_type = first_fail.get("error_type") or (
                        "timeout" if "timeout" in str(first_fail.get("error", "")).lower() else "llm_error"
                    )
                    llm_error_message = first_fail.get("error") or first_fail.get("error_message")
                    llm_error_occurred_at = datetime.now(timezone.utc)
                elif metrics_data.get("timeout_stage") not in (None, "none"):
                    llm_error_type = "timeout"
                    llm_error_message = metrics_data.get("timeout_reason") or "LLM call timed out"
                    llm_error_occurred_at = datetime.now(timezone.utc)

                # Determine success based on orchestrator result and TODO outcomes
                success = bool(result.ok)
                todo_failures = [t for t in todos_data if t.status not in ("completed",)]
                if todo_failures:
                    success = False
                    if not errors_list:
                        errors_list.append(f"{len(todo_failures)} TODO(s) failed")

                if success and (output_text is None or str(output_text).strip() == ""):
                    output_text = "Run completed; see steps and metrics for details."
            else:
                # Handle case where result is None (timeout) or result.ok is False
                if result:
                    error_msg = _coerce_error_message(result.error, "Orchestrator returned failure")
                else:
                    error_msg = "Orchestrator timed out"
                errors_list.append(error_msg)

        except Exception as exc:
            error_msg = f"Orchestrator error: {exc!s}"
            log.warning("agent_run.background.orchestrator_failed", error=str(exc), run_id=str(run_id))
            errors_list.append(error_msg)
            
            # Classify LLM error if it appears to be from LLM (Task C.10)
            llm_error_type = classify_llm_error(error_msg)
            llm_error_message = error_msg
            llm_error_occurred_at = datetime.now(timezone.utc)

        # Fallback demo if orchestrator failed
        if (not success) and not steps_data:
            output_text = f"(demo) You said: {prompt}"
            # B1: Normalize error for fallback case too
            normalized_fallback_error = _normalize_error_field(error_msg)
            steps_data = [
                OrchestrationStepOutput(
                    step_id="fallback",
                    output={"error": error_msg or "No orchestrator found; returning demo echo."},
                    error=normalized_fallback_error,
                )
            ]
            used_model = None

        # Calculate latency
        latency_ms = int((time.monotonic_ns() - start_ns) / 1_000_000)
        duration_seconds = latency_ms / 1000.0
        
        # Track metrics: record run completion
        if METRICS_AVAILABLE and agent_metrics:
            agent_metrics.dec_running(tenant_id=tenant_id)
            
            if success:
                agent_metrics.record_run_success(tenant_id=tenant_id)
                agent_metrics.record_run_duration(duration_seconds, "succeeded", tenant_id=tenant_id)
            else:
                # Determine failure type from error message
                failure_type_str = FailureType.RUN_TIMEOUT.value if (errors_list and "timeout" in errors_list[0].lower()) else FailureType.ORCHESTRATOR_ERROR.value
                agent_metrics.record_run_failure(failure_type_str, tenant_id=tenant_id)
                agent_metrics.record_run_duration(duration_seconds, "failed", tenant_id=tenant_id)
            
            # Record TODO count
            if todos_data:
                agent_metrics.record_todo_count(len(todos_data), tenant_id=tenant_id)

        # Serialize Pydantic models to JSON for database storage
        from src.utils.jsonable import to_jsonable
        steps_json = [to_jsonable(step.model_dump()) for step in steps_data] if steps_data else None
        todos_json = [to_jsonable(todo.model_dump()) for todo in todos_data] if todos_data else None

        # Extract final output from final-tools-output step if present
        final_output_obj = output_text
        
        # For failed runs, construct structured error output
        if not success and errors_list:
            # Determine failure type from error message
            failure_type_str = FailureType.RUN_TIMEOUT.value if "timeout" in errors_list[0].lower() else FailureType.ORCHESTRATOR_ERROR.value
            
            # Count completed/failed todos
            todos_completed = len([t for t in todos_data if t.status == "completed"])
            todos_failed = len([t for t in todos_data if t.status in ("failed", "failed_due_to_timeout")])
            
            # Build timeout reason if this was a timeout failure
            timeout_reason = None
            if failure_type_str == FailureType.RUN_TIMEOUT.value:
                timeout_stage = metrics_data.get("timeout_stage", "unknown")
                llm_attempted = metrics_data.get("llm_attempted_calls", 0)
                llm_successful = metrics_data.get("llm_successful_calls", 0)
                
                if llm_attempted == 0:
                    timeout_reason = f"Timeout occurred during {timeout_stage} before any LLM calls"
                elif llm_successful == 0:
                    timeout_reason = f"Timeout occurred during {timeout_stage} after {llm_attempted} failed LLM call(s)"
                else:
                    timeout_reason = f"Timeout occurred during {timeout_stage} after {llm_successful}/{llm_attempted} successful LLM call(s)"
            
            final_output_obj = {
                "error": errors_list[0] if errors_list else "Orchestration failed",
                "failure_type": failure_type_str,
                "todos_completed": todos_completed,
                "todos_failed": todos_failed,
                "partial_results": True if todos_completed > 0 else False,
            }
            
            if timeout_reason:
                final_output_obj["timeout_reason"] = timeout_reason
                # Also add to warnings for API response
                warnings_list.append(timeout_reason)
        
        # Otherwise extract from final-tools-output step
        for step in steps_data:
            if hasattr(step, 'step_id') and step.step_id == "final-tools-output":
                if hasattr(step, 'output') and step.output:
                    final_output_obj = to_jsonable(step.output)
                    break
        
        # Update run record with results
        final_status = "succeeded" if success else "failed"
        log.info(
            "agent_run.background.updating_status",
            run_id=str(run_id),
            from_status="running",
            to_status=final_status,
            latency_ms=latency_ms,
        )
        
        # B5: Prepare comprehensive metrics object
        final_metrics = {"overall_ms": latency_ms}
        if metrics_data:
            final_metrics.update(metrics_data)
        
        # B5: Ensure critical metrics are always present (even if 0)
        final_metrics.setdefault("llm_attempted_calls", metrics_data.get("llm_attempted_calls", 0) if metrics_data else 0)
        final_metrics.setdefault("llm_successful_calls", metrics_data.get("llm_successful_calls", 0) if metrics_data else 0)
        final_metrics.setdefault("timeout_stage", metrics_data.get("timeout_stage") if metrics_data else None)
        final_metrics.setdefault("configured_run_timeout_seconds", RUN_TIMEOUT_SECONDS)
        final_metrics.setdefault("configured_step_timeout_seconds", STEP_TIMEOUT_SECONDS)
        final_metrics.setdefault("run_timeout_budget_ms", RUN_TIMEOUT_SECONDS * 1000)
        
        # Centralize tools_executed computation and persist it for analytics/UI
        _final_tools_executed = int(final_metrics.get("tool_calls", 0))
        final_metrics["tools_executed"] = _final_tools_executed
        
        log.info(
            "agent_run.background.final_metrics",
            run_id=str(run_id),
            metrics_keys=list(final_metrics.keys()),
            has_llm=("llm" in final_metrics),
            has_tools=(_final_tools_executed > 0),  # Derived from actual tool_calls count
            tools_executed=_final_tools_executed,
            llm_attempted=final_metrics.get("llm_attempted_calls", 0),
            llm_successful=final_metrics.get("llm_successful_calls", 0),
        )
        
        # B2: Get the run object to access its stable trace_id
        run = AgentRunRepository.get_by_id(db, run_id)
        
        # Record provenance with stable trace_id
        ev = record_provenance(
            actor="api",
            action="agent.run",
            resource=f"/agent-runs/{run_id}",
            input={"prompt": prompt, "params": params},
            output={"output": output_text, "steps": steps_json or []},
            meta={"user": user_id, "session_id": str(session_id), "model": used_model},
            duration_ms=latency_ms,
            trace_id=run.trace_id,  # B2: Use stable trace_id from run, not run_id
        )
        
        normalized_output = normalize_run_output(final_output_obj)
        serialized_output = to_jsonable(normalized_output) if normalized_output is not None else None

        AgentRunRepository.update_status(
            db,
            run_id=run_id,
            status=final_status,
            model=used_model,
            latency_ms=latency_ms,
            finished_at=datetime.now(timezone.utc),
            output=serialized_output,
            todos=to_jsonable(todos_json) if todos_json else None,
            steps=to_jsonable(steps_json) if steps_json else None,
            warnings=warnings_list if warnings_list else None,
            event_id=ev.event_id,
            metrics=to_jsonable(final_metrics) if final_metrics else None,
            # LLM error tracking (Task C.10)
            llm_error_type=llm_error_type,
            llm_error_message=llm_error_message,
            llm_error_occurred_at=llm_error_occurred_at,
        )
        db.commit()
        
        log.info(
            "agent_run.background.completed",
            run_id=str(run_id),
            status=final_status,
            latency_ms=latency_ms,
        )
        
    except Exception as exc:
        # B3: Calculate latency even in fatal error path
        fatal_latency_ms = int((time.monotonic_ns() - start_ns) / 1_000_000)
        
        log.error(
            "agent_run.background.fatal_error",
            run_id=str(run_id),
            error=str(exc),
            latency_ms=fatal_latency_ms,
        )
        # Mark run as failed with structured output
        try:
            # Classify fatal error (Task C.10)
            fatal_error_msg = f"Background execution failed: {exc!s}"
            fatal_error_type = classify_llm_error(fatal_error_msg)
            
            # B3: Build minimal metrics for fatal error
            fatal_metrics = {
                "overall_ms": fatal_latency_ms,
                "llm_attempted_calls": 0,  # Unknown in fatal path
                "llm_successful_calls": 0,
                "tool_calls": 0,
                "tool_errors": 0,
                "timeout_stage": "none",
            }
            fatal_metrics.setdefault("configured_run_timeout_seconds", RUN_TIMEOUT_SECONDS)
            fatal_metrics.setdefault("configured_step_timeout_seconds", STEP_TIMEOUT_SECONDS)
            fatal_metrics.setdefault("run_timeout_budget_ms", RUN_TIMEOUT_SECONDS * 1000)
            
            AgentRunRepository.update_status(
                db,
                run_id=run_id,
                status="failed",
                output={
                    "error": fatal_error_msg,
                    "failure_type": FailureType.ORCHESTRATOR_ERROR.value,
                },
                latency_ms=fatal_latency_ms,  # B3: Include latency
                metrics=fatal_metrics,  # B3: Include basic metrics
                finished_at=datetime.now(timezone.utc),
                # LLM error tracking
                llm_error_type=fatal_error_type,
                llm_error_message=fatal_error_msg,
                llm_error_occurred_at=datetime.now(timezone.utc),
            )
            db.commit()
        except Exception as db_exc:
            log.error(
                "agent_run.background.db_update_failed",
                run_id=str(run_id),
                error=str(db_exc),
            )
    finally:
        db.close()


@router.post(
    "",
    response_model=RunResponse,
    status_code=201,
    summary="Create an agent run (async)",
    description=(
        "**🚀 ASYNC ENDPOINT - Returns immediately with run_id**\n\n"
        "This endpoint creates an agent run and schedules it for **background execution**. "
        "It returns immediately (typically < 100ms) with:\n"
        "- `status: 'queued'` - Run is scheduled but not yet started\n"
        "- `run_id` - Unique identifier to poll for completion\n"
        "- `Location` header - URI to check run status\n\n"
        "**📊 Polling workflow (recommended):**\n"
        "1. POST /v1/agent-runs → Get `run_id` (status='queued')\n"
        "2. Poll GET /v1/agent-runs/{run_id} every 2-5s\n"
        "3. When `status` ∈ ['succeeded', 'failed', 'cancelled'], orchestration is complete\n"
        "4. Fetch GET /v1/agent-runs/{run_id}/steps for detailed execution trace\n\n"
        "**Status lifecycle:**\n"
        "- `queued` → Run created, waiting for worker\n"
        "- `running` → Orchestrator executing (may take 5-15+ min for NL→Cypher on CPU)\n"
        "- `succeeded` → Completed successfully with output\n"
        "- `failed` → Orchestration error (see `errors` field)\n\n"
        "**Why we need this endpoint:**\n"
        "- Solve one-off tasks without setting up a full session\n"
        "- Get quick answers with a single request\n"
        "- Avoid session management overhead for simple scenarios\n"
        "- Auto-create sessions if you want results persisted\n\n"
        "**What it does:**\n"
        "- Creates agent run record with status='queued'\n"
        "- Schedules background orchestration (non-blocking)\n"
        "- Uses existing session (if you provide session_id) or auto-creates one\n"
        "- Returns immediately so you can poll for completion\n"
        "- Orchestrator updates run status as it progresses\n\n"
        "**Access:** Users can create runs (auto-created runs belong to that user); admins can create on behalf of others; authenticated only\n\n"
        "**Behavior:** Idempotency (Idempotency-Key header for safe retries), auto-session creation, latency tracking (ms), audit logging with trace ID, per-user rate limiting"
    ),
    name="create_agent_run",
    responses={
        201: {
            "description": "Run created and scheduled for execution (status='queued')",
            "model": RunResponse,
            "headers": {
                "Location": {"description": "URI to poll for run status: GET /v1/agent-runs/{run_id}"},
                "Idempotency-Key": {"description": "Echo of the Idempotency-Key header if provided"},
                "X-Request-Id": {"description": "Request correlation ID for tracing"},
            },
        },
        400: {
            "description": "Bad Request - Invalid request body or parameters (e.g., invalid session_id)",
            "content": {
                "application/problem+json": {
                    "schema": {"$ref": "#/components/schemas/ProblemDetails"},
                    "example": {
                        "type": "about:blank",
                        "title": "Bad Request",
                        "status": 400,
                        "detail": "Invalid session_id format",
                        "instance": "/v1/agents/runs",
                        "extensions": {"correlation_id": "req-123456", "timestamp": "2025-10-21T10:30:00Z"},
                    },
                }
            },
        },
        404: {
            "description": "Not Found - Session ID provided but session doesn't exist or not accessible",
            "content": {
                "application/problem+json": {
                    "schema": {"$ref": "#/components/schemas/ProblemDetails"},
                    "example": {
                        "type": "about:blank",
                        "title": "Not Found",
                        "status": 404,
                        "detail": "Session not found",
                        "instance": "/v1/agents/runs",
                        "extensions": {"correlation_id": "req-123456", "timestamp": "2025-10-21T10:30:00Z"},
                    },
                }
            },
        },
    },
)
async def create_agent_run(
    request: Request,
    req: CreateRunRequest,
    response: Response,
    background_tasks: BackgroundTasks,
    db: DBSession = Depends(get_db),
    user: Principal = Depends(require_perms(["user:me"])),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    use_jobs: bool = False,
) -> dict[str, Any]:
    """Create and execute an agent run asynchronously."""
    # Check rate limit
    rate_limiter = RateLimitHandler(user_id=user.sub)
    await rate_limiter.check("runs:create")

    # Readiness gate: reject runs until orchestrator is fully initialized
    from src.services.orchestrator import Orchestrator
    if not Orchestrator.is_ready():
        raise HTTPException(status_code=503, detail="Agent service warming up; try again shortly.")

    start_ns = time.monotonic_ns()
    
    # Capture request ID for tracing
    request_id = get_request_id()
    
    handler = IdempotencyHandler(request, response, user.sub, db, idempotency_key)

    # Check for replay
    if idempotency_key:
        cached = handler.check()
        if cached:
            response.headers["Idempotency-Replayed"] = "true"
            response.status_code = cached["status_code"]
            cached_model = RunResponse(**cached["body"])
            return _run_response_to_json(cached_model)

    # Get or create session
    session_id = req.session_id
    # Use tenant from JWT if available, otherwise use Global tenant
    tenant_id = getattr(user, "tenant_id", None) or user.raw.get("tid", "tenant-67e5ca68")

    if session_id:
        # Validate session exists and is owned by user
        is_admin = "admin:all" in user.scopes
        if is_admin:
            session = AgentSessionRepository.get_by_id(db, session_id)
        else:
            session = AgentSessionRepository.get_by_id_and_owner(db, session_id, user.sub)

        if not session:
            agent_errors.session_not_found(
                session_id=session_id,
                instance="/agent-runs",
            )
    else:
        # Create new session automatically
        session = AgentSessionRepository.create(
            db,
            user_id=user.sub,
            tenant_id=tenant_id,
            manager=req.manager,
            tools=req.tools,
            temperature=req.temperature,
            max_steps=req.max_steps,
            metadata=req.metadata or {},
        )
        session_id = session.session_id
        db.flush()

    # Generate stable trace_id for this run (will persist across all requests)
    stable_trace_id = str(uuid.uuid4())
    
    # Store initial request_id in session metadata for traceability
    initial_metadata = req.metadata or {}
    if request_id:
        initial_metadata["initial_request_id"] = request_id
    
    # Fetch DB default model configuration (Task B.7)
    # This persists the model config at run creation time
    model_config = None
    model_instance_name = None
    model_id = None
    provider_name = None
    provider_id = None
    config_source = None
    
    try:
        model_config = model_instance_repo.get_default(scope="global", tenant_id=None)
        if model_config:
            model_instance_name = model_config.instance_name
            model_id = model_config.provider_model_id
            provider_name = model_config.provider_name
            provider_id = model_config.provider_id
            config_source = model_config.source
            log.info(
                "agent_run.model_config_loaded",
                run_trace_id=stable_trace_id,
                instance_name=model_instance_name,
                model_id=model_id,
                provider_name=provider_name,
                config_source=config_source,
            )
        else:
            log.warning(
                "agent_run.model_config_missing",
                run_trace_id=stable_trace_id,
                message="No DB default model found - run will use orchestrator default"
            )
    except Exception as e:
        log.error(
            "agent_run.model_config_error",
            run_trace_id=stable_trace_id,
            error=str(e),
            message="Failed to load DB default model - run will use orchestrator default"
        )
    
    # Prepare metadata and params up-front so we can reuse the same dict everywhere
    params_metadata = dict(initial_metadata)

    # Create run record with status="queued" and stable trace_id
    run = AgentRunRepository.create(
        db,
        session_id=session_id,
        user_id=user.sub,
        tenant_id=tenant_id,
        model=model_id,  # Legacy field - use model_id for backward compatibility
        manager=req.manager,
        trace_id=stable_trace_id,  # Set stable trace ID at creation
        request_id=request_id,  # Store HTTP request ID for correlation
        # New model config fields (Task B.7)
        model_instance_name=model_instance_name,
        model_id=model_id,
        provider_name=provider_name,
        provider_id=provider_id,
        config_source=config_source,
        metadata=params_metadata,
    )
    run_id = run.run_id
    
    # Set status to queued (will transition to running in background task)
    from datetime import datetime, timezone
    run.status = "queued"
    run.created_at = datetime.now(timezone.utc)
    
    # Commit immediately so the run is persisted and visible to polls
    db.commit()
    log.info("agent_run.created", run_id=str(run_id), status="queued")
    
    # Track metrics: increment queued counter
    if METRICS_AVAILABLE and agent_metrics:
        agent_metrics.inc_queued(tenant_id=tenant_id)

    # Build params dict for orchestrator
    params = {
        "temperature": req.temperature,
        "max_steps": req.max_steps,
        "metadata": params_metadata,
        "force_full_agentic": bool(req.force_full_agentic),
    }
    if req.manager:
        params["manager"] = req.manager
    if req.preferred_workers:
        params["preferred_workers"] = req.preferred_workers
    if req.llm_preferences:
        params["llm_preferences"] = req.llm_preferences
    if req.agent_role:
        params["agent_role"] = req.agent_role
    if req.force_full_agentic:
        params["disable_trivial_fast_path"] = True

    memgraph_force_llm = _coerce_truthy(os.getenv("MEMGRAPH_FORCE_LLM", "false"))
    default_force_llm_flag = "true" if os.getenv("APP_ENV") == "test" else "false"
    force_llm_memgraph_tests = _coerce_truthy(os.getenv("FORCE_LLM_MEMGRAPH_TESTS", default_force_llm_flag))
    if "memgraph_force_llm" in params_metadata:
        memgraph_force_llm = _coerce_truthy(params_metadata["memgraph_force_llm"])
    if memgraph_force_llm:
        params_metadata["memgraph_force_llm"] = True
        params["memgraph_force_llm"] = True
    if "memgraph_nl_verbose_answer" in params_metadata:
        params["memgraph_nl_verbose_answer"] = _coerce_truthy(params_metadata["memgraph_nl_verbose_answer"])
    
    # Enhance params with NL prompt hints when running in Memgraph test mode
    prompt_hints = get_prompt_hints(req.prompt)
    if prompt_hints:
        inferred_category = prompt_hints.get("category")
        inferred_todo_mode = prompt_hints.get("todo_mode")
        if inferred_category:
            params.setdefault("category", inferred_category)
        if inferred_todo_mode:
            params.setdefault("todo_mode", inferred_todo_mode)
        params.setdefault("memgraph_prompt_id", prompt_hints.get("id"))
        params.setdefault("memgraph_prompt_index", prompt_hints.get("index"))
        params.setdefault("memgraph_prompt_notes", prompt_hints.get("notes"))
        params.setdefault("memgraph_prompt_expected_pattern", prompt_hints.get("expected_pattern"))
        params.setdefault(
            "memgraph_prompt_expected_contains",
            prompt_hints.get("expected_cypher_contains", []),
        )
        params.setdefault("memgraph_prompt_random", prompt_hints.get("random"))
        params.setdefault("memgraph_prompt_limit", prompt_hints.get("limit_hint"))
        params.setdefault("memgraph_prompt_allowed_for_admin", prompt_hints.get("allowed_for_admin"))
        params.setdefault("memgraph_prompt_allowed_for_user", prompt_hints.get("allowed_for_user"))
        if "memgraph_prompt_random" not in params_metadata:
            params_metadata["memgraph_prompt_random"] = prompt_hints.get("random")
        if "memgraph_prompt_limit" not in params_metadata:
            params_metadata["memgraph_prompt_limit"] = prompt_hints.get("limit_hint")
        if force_llm_memgraph_tests and not memgraph_force_llm:
            params_metadata["memgraph_force_llm"] = True
            params["memgraph_force_llm"] = True
            memgraph_force_llm = True
        log.info(
            "agent_run.prompt_hints_applied",
            prompt_id=prompt_hints.get("id"),
            category=inferred_category,
            todo_mode=inferred_todo_mode,
        )

    # B4: Add principal and tenant_id for RBAC enforcement in MCP tools
    principal = serialize_principal(user, tenant_id=tenant_id)
    # If caller explicitly assigns admin role, propagate as permissions/roles
    if req.agent_role and str(req.agent_role).lower() == "admin":
        perms = set(principal.get("permissions", []))
        roles = set(principal.get("roles", []))
        perms.add("admin:all")
        roles.add("admin")
        principal["permissions"] = sorted(perms)
        principal["roles"] = sorted(roles)
        # Relax RBAC to grant tool scopes downstream
        principal.setdefault("rbac_enforced", True)
        scopes = set(principal.get("scopes", []))
        scopes.update({"tools:read", "tools:basic"})
        principal["scopes"] = sorted(scopes)
    params["principal"] = principal
    params["tenant_id"] = tenant_id

    # Store principal summary in metadata for traceability/auditing
    params_metadata.setdefault(
        "auth",
        {
            "principal_id": principal.get("id"),
            "tenant_id": tenant_id,
            "permissions": principal.get("permissions", []),
            "roles": principal.get("roles", []),
        },
    )

    # Include resolved prompt hints in metadata for traceability
    if prompt_hints:
        params_metadata.setdefault(
            "memgraph_prompt",
            {
                "id": prompt_hints.get("id"),
                "category": prompt_hints.get("category"),
                "todo_mode": prompt_hints.get("todo_mode"),
                "notes": prompt_hints.get("notes"),
                "expected_pattern": prompt_hints.get("expected_pattern"),
                "expected_cypher_contains": prompt_hints.get("expected_cypher_contains", []),
                "allowed_for_admin": prompt_hints.get("allowed_for_admin"),
                "allowed_for_user": prompt_hints.get("allowed_for_user"),
            },
        )
    params["metadata"] = params_metadata

    # ──────────────────────────────────────────────────────────────────────────
    # OPTION A: Use Jobs Worker for more robust async execution
    # ──────────────────────────────────────────────────────────────────────────
    if use_jobs:
        # Create job via JobsService instead of using background_tasks
        from src.config import settings
        use_postgres_jobs = getattr(settings, "USE_POSTGRES_JOBS", False)
        if isinstance(use_postgres_jobs, str):
            use_postgres_jobs = use_postgres_jobs.lower() in ("true", "1", "yes")
        
        if not use_postgres_jobs:
            raise HTTPException(
                status_code=503, 
                detail="Jobs worker not enabled. Set USE_POSTGRES_JOBS=true to use use_jobs=true."
            )
        
        try:
            from src.services.jobs_service import JobsService
            jobs_service = JobsService(db)
            
            # Build agent.run job payload
            job_payload = {
                "prompt": req.prompt,
                "user_id": user.sub,
                "tenant_id": tenant_id,
                "session_id": str(session_id) if session_id else None,
                "run_id": str(run_id),  # Link to the AgentRun we already created
                "model": req.model,
                "manager": req.manager,
                "temperature": req.temperature,
                "max_steps": req.max_steps,
                "metadata": params_metadata,
                "trace_id": stable_trace_id,
                "request_id": request_id,
                "principal": principal,
            }
            
            # Create job (worker will execute it)
            job, is_new = jobs_service.create_job(
                owner_sub=user.sub,
                tenant_id=tenant_id,
                job_type="agent.run",
                payload=job_payload,
                idempotency_key=idempotency_key,
                priority=0,
            )
            
            # Update run metadata to reference the job
            run.run_metadata = {
                **(run.run_metadata or {}),
                "job_id": str(job.id),
                "execution_mode": "jobs_worker",
            }
            db.commit()
            
            log.info(
                "agent_run.job_created",
                run_id=str(run_id),
                job_id=str(job.id),
                execution_mode="jobs_worker",
            )
            
            # Build response
            _queued_result, queued_payload = _prepare_run_response_payload(
                run,
                blank_runtime_fields=True,
            )
            
            # Add job_id to response
            queued_payload["job_id"] = str(job.id)
            queued_payload["execution_mode"] = "jobs_worker"
            
            # Cache idempotent result
            if idempotency_key:
                await handler.cache(
                    request_body=req.model_dump(mode="json"),
                    response_body=queued_payload,
                )
            
            # Set Location header
            try:
                loc = request.url_for("get_agent_run", run_id=str(run_id))
            except Exception:
                loc = f"/v1/agent-runs/{run_id}"
            
            response.headers["Location"] = str(loc)
            response.headers["X-Job-Id"] = str(job.id)
            
            if idempotency_key:
                response.headers["Idempotency-Key"] = idempotency_key
            
            for key, value in add_standard_headers({}).items():
                response.headers[key] = value
            
            response.status_code = 202
            return queued_payload
            
        except ImportError as e:
            log.error("agent_run.jobs_import_error", error=str(e))
            raise HTTPException(
                status_code=503,
                detail="Jobs service not available. Ensure PostgreSQL jobs are configured."
            )
        except Exception as e:
            log.error("agent_run.job_creation_failed", error=str(e), run_id=str(run_id))
            raise HTTPException(status_code=500, detail=f"Failed to create job: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # OPTION B (DEFAULT): Use FastAPI BackgroundTasks
    # ──────────────────────────────────────────────────────────────────────────
    # Schedule background execution (non-blocking)
    background_tasks.add_task(
        execute_agent_run_background,
        run_id=run_id,
        prompt=req.prompt,
        user_id=user.sub,
        session_id=str(session_id),
        tenant_id=tenant_id,
        params=params,
        request_id=request_id,
    )
    
    log.info(
        "agent_run.scheduled",
        run_id=str(run_id),
        session_id=str(session_id),
        user_id=user.sub,
    )

    # Calculate endpoint latency (just scheduling time, not orchestration)
    latency_ms = int((time.monotonic_ns() - start_ns) / 1_000_000)

    # Build immediate response with status='queued'
    _queued_result, queued_payload = _prepare_run_response_payload(
        run,
        blank_runtime_fields=True,
    )

    # Cache idempotent result
    if idempotency_key:
        await handler.cache(
            request_body=req.model_dump(mode="json"),
            response_body=queued_payload,
        )

    # Set Location header
    try:
        loc = request.url_for("get_agent_run", run_id=str(run_id))
    except Exception:
        loc = f"/v1/agent-runs/{run_id}"

    response.headers["Location"] = str(loc)

    # Add Idempotency-Key response header if provided
    if idempotency_key:
        response.headers["Idempotency-Key"] = idempotency_key

    # Add standard headers (X-Request-Id)
    for key, value in add_standard_headers({}).items():
        response.headers[key] = value

    # Add rate limit headers
    await add_rate_limit_headers(response, user.sub, "runs:create")

    return queued_payload


# Colon alias for backwards compatibility: POST /v1/agent-runs:run
@router.post(
    path=":run",
    include_in_schema=False,
)
async def create_agent_run_colon(
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    db: DBSession = Depends(get_db),
    user: UserInfo = Depends(require_perms(["user:me"])),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    """Backwards-compatible colon action alias."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    req = CreateRunRequest(**(body or {}))
    return await create_agent_run(request, req, response, background_tasks, db, user, idempotency_key)


@router.get(
    "/{run_id}",
    name="get_agent_run",
    summary="Get agent run by ID",
    response_model=RunResponse,
    description=(
        "**Why we need this endpoint:**\n"
        "- Check results of a run submitted earlier\n"
        "- Access generated output and step-by-step execution details\n"
        "- Track execution metrics (duration, model used)\n"
        "- Verify run succeeded or debug why it failed\n\n"
        "**What it does:**\n"
        "- Returns complete details of a previously-created agent run\n"
        "- Includes final output, execution metrics, and all steps taken\n"
        "- Shows which session the run was linked to (if any)\n"
        "- Provides tracing info (trace_id, event_id) for debugging\n"
        "- Validates you have permission to view this specific run\n\n"
        "**Access:** Users see runs they created; admins see any run; authenticated only\n\n"
        "**Behavior:** Ownership validation, ETag support (304 if unchanged), includes tracing IDs for log correlation, shows execution timestamps"
    ),
    responses={
        200: {
            "description": "Run found and returned with complete details including output",
            "model": RunResponse,
            "headers": {
                "ETag": {"description": "Entity tag for caching support (If-None-Match)"},
                "Vary": {"description": "Indicates that response varies by Authorization header"},
                "X-Request-Id": {"description": "Request correlation ID for tracing"},
            },
        },
        304: {"description": "Not Modified - run details unchanged since last check (ETag matched)"},
        404: {
            "description": "Not Found - Run not found or you don't have permission to view it",
            "content": {
                "application/problem+json": {
                    "schema": {"$ref": "#/components/schemas/ProblemDetails"},
                    "example": {
                        "type": "about:blank",
                        "title": "Not Found",
                        "status": 404,
                        "detail": "Run not found",
                        "instance": "/v1/agents/runs/{run_id}",
                        "extensions": {"correlation_id": "req-123456", "timestamp": "2025-10-21T10:30:00Z"},
                    },
                }
            },
        },
    },
)
async def get_agent_run(
    run_id: str,
    response: Response,
    db: DBSession = Depends(get_db),
    user: UserInfo = Depends(require_perms(["user:me"])),
    if_none_match: str | None = Header(None, alias="If-None-Match"),
) -> dict[str, Any]:
    """Get run by ID with ownership check and ETag support."""
    is_admin = "admin:all" in user.scopes

    # Parse UUID
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        agent_errors.raise_problem(
            status_code=400,
            title="Invalid Run ID",
            detail=f"Run ID must be a valid UUID format, got: {run_id}",
            error_code="invalid_run_id",
            instance=f"/agent-runs/{run_id}",
            extensions={"run_id": run_id},
        )

    # Get run with ownership check
    if is_admin:
        run = AgentRunRepository.get_by_id(db, run_uuid)
    else:
        run = AgentRunRepository.get_by_id_and_owner(db, run_uuid, user.sub)

    if not run:
        agent_errors.run_not_found(
            run_id=run_id,
            instance=f"/agent-runs/{run_id}",
        )

    # Build response
    result, result_payload = _prepare_run_response_payload(run)
    
    # Note: request_id is intentionally not set here - it represents the HTTP request
    # that CREATED the run. For observability of the GET request itself, use X-Request-Id header.
    # If you need a stable identifier across all requests for this run, use trace_id instead.

    # Optionally fetch steps if needed
    # steps = AgentStepRepository.list_by_session(db, run.session_id)
    # result.steps = [StepResponse.model_validate(s) for s in steps]

    # Generate and validate ETag
    from src.utils.etag import generate_etag, validate_etag

    current_etag = generate_etag(result_payload, weak=False)

    # Check If-None-Match header
    if validate_etag(if_none_match, current_etag):
        headers = {"ETag": current_etag, "Vary": "Authorization"}
        headers = add_standard_headers(headers)
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)

    response.headers["ETag"] = current_etag
    response.headers["Vary"] = "Authorization"

    # Add standard headers (X-Request-Id)
    for key, value in add_standard_headers({}).items():
        response.headers[key] = value

    return result_payload


@router.get(
    "/{run_id}/steps",
    name="get_agent_run_steps",
    summary="Get execution steps for an agent run",
    description=(
        "**Why we need this endpoint:**\n"
        "- View detailed step-by-step execution of an agent run\n"
        "- Debug which steps were executed and in what order\n"
        "- Inspect inputs/outputs for each step\n"
        "- Track execution flow for complex agent workflows\n\n"
        "**What it returns:**\n"
        "- Array of steps executed during the agent run\n"
        "- Each step includes: action, inputs, outputs, metadata\n"
        "- Returns empty array if no steps stored or run not found\n\n"
        "**Access:** Users see steps for runs they created; admins see any run's steps\n"
    ),
    responses={
        200: {
            "description": "Steps retrieved successfully (may be empty array)",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "examples": {
                        "with_steps": {
                            "summary": "Run with execution steps",
                            "value": [
                                {
                                    "id": "step-1",
                                    "action": "catalog.discover",
                                    "input": {"model": "test-model-latest"},
                                    "output": {"tools_found": 41},
                                    "status": "completed",
                                },
                                {
                                    "id": "step-2",
                                    "action": "llm:planner",
                                    "input": {"prompt": "Analyze tools"},
                                    "output": {"analysis": "Found 9 LLM tools and 32 MCP tools"},
                                    "status": "completed",
                                },
                            ],
                        },
                        "no_steps": {
                            "summary": "Run with no steps",
                            "value": [],
                        },
                    },
                }
            },
        },
        404: {
            "description": "Run not found or you don't have permission to view it",
            "content": {
                "application/problem+json": {
                    "schema": {"$ref": "#/components/schemas/ProblemDetails"},
                }
            },
        },
    },
)
async def get_agent_run_steps(
    run_id: str,
    response: Response,
    db: DBSession = Depends(get_db),
    user: UserInfo = Depends(require_perms(["user:me"])),
) -> list[dict[str, Any]]:
    """Get execution steps for an agent run."""
    is_admin = "admin:all" in user.scopes

    # Parse UUID
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        agent_errors.raise_problem(
            status_code=400,
            title="Invalid Run ID",
            detail=f"Run ID must be a valid UUID format, got: {run_id}",
            error_code="invalid_run_id",
            instance=f"/agent-runs/{run_id}/steps",
            extensions={"run_id": run_id},
        )

    # Get run with ownership check
    if is_admin:
        run = AgentRunRepository.get_by_id(db, run_uuid)
    else:
        run = AgentRunRepository.get_by_id_and_owner(db, run_uuid, user.sub)

    if not run:
        agent_errors.run_not_found(
            run_id=run_id,
            instance=f"/agent-runs/{run_id}/steps",
        )

    # Get steps from run (stored in steps column as JSONB)
    # Note: run is an ORM object, use attribute access not .get()
    steps = run.steps if run.steps is not None else []
    
    # Ensure steps is a list
    if not isinstance(steps, list):
        steps = []

    # Add standard headers
    for key, value in add_standard_headers({}).items():
        response.headers[key] = value

    return steps


@router.get(
    "/{run_id}/outputs",
    name="get_agent_run_outputs",
    summary="Get outputs for an agent run",
    description=(
        "**Why we need this endpoint:**\n"
        "- View the outputs generated during agent execution\n"
        "- Access structured data produced by each step\n"
        "- Debug what data was stored/cached by the agent\n"
        "- Track data flow between orchestration steps\n\n"
        "**What it returns:**\n"
        "- Array of outputs generated during the run\n"
        "- Each output includes: step_id, action, output data, todo_index\n"
        "- Returns empty array if no outputs stored yet (200 OK, not 404)\n"
        "- 404 only if the run itself doesn't exist\n\n"
        "**Access:** Users see outputs for runs they created; admins see any run's outputs\n"
    ),
    responses={
        200: {
            "description": "Outputs retrieved successfully (may be empty array if no outputs yet)",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "examples": {
                        "with_outputs": {
                            "summary": "Run with outputs",
                            "value": [
                                {
                                    "step_id": "step-1",
                                    "action": "catalog.discover",
                                    "output": {"tools": [{"name": "tool1"}]},
                                    "todo_index": 0,
                                },
                                {
                                    "step_id": "step-2",
                                    "action": "store_tools",
                                    "output": {"ok": True, "stored_count": 41},
                                    "todo_index": 1,
                                },
                            ],
                        },
                        "no_outputs": {
                            "summary": "Run exists but has no outputs yet",
                            "value": [],
                        },
                    },
                }
            },
        },
        404: {
            "description": "Run not found or you don't have permission to view it",
            "content": {
                "application/problem+json": {
                    "schema": {"$ref": "#/components/schemas/ProblemDetails"},
                }
            },
        },
    },
)
async def get_agent_run_outputs(
    run_id: str,
    response: Response,
    db: DBSession = Depends(get_db),
    user: UserInfo = Depends(require_perms(["user:me"])),
) -> list[dict[str, Any]]:
    """Get outputs for an agent run. Returns 200 with empty list if run exists but has no outputs."""
    is_admin = "admin:all" in user.scopes

    # Parse UUID
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        agent_errors.raise_problem(
            status_code=400,
            title="Invalid Run ID",
            detail=f"Run ID must be a valid UUID format, got: {run_id}",
            error_code="invalid_run_id",
            instance=f"/agent-runs/{run_id}/outputs",
            extensions={"run_id": run_id},
        )

    # Get run with ownership check
    if is_admin:
        run = AgentRunRepository.get_by_id(db, run_uuid)
    else:
        run = AgentRunRepository.get_by_id_and_owner(db, run_uuid, user.sub)

    # 404 only if run truly doesn't exist
    if not run:
        agent_errors.run_not_found(
            run_id=run_id,
            instance=f"/agent-runs/{run_id}/outputs",
        )

    # Get outputs from orchestration result stored in run
    # Outputs might be stored in steps with output data or in a separate outputs field
    outputs = []
    
    # Check if there's a dedicated outputs field (some orchestrator versions store it)
    if hasattr(run, 'outputs') and run.outputs is not None:
        if isinstance(run.outputs, list):
            outputs = run.outputs
    
    # Fallback: extract outputs from steps (steps with "output" field)
    if not outputs and run.steps:
        for step in run.steps:
            if isinstance(step, dict) and "output" in step:
                outputs.append(step)

    # Ensure outputs is always a list (empty list if none)
    if not isinstance(outputs, list):
        outputs = []

    # Add standard headers
    for key, value in add_standard_headers({}).items():
        response.headers[key] = value

    # Return 200 with empty list if run exists but has no outputs
    return outputs
