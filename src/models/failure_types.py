"""
Failure type enumeration for agent orchestration errors.

Provides structured error classification for timeout and execution failures.
"""

from enum import Enum


class FailureType(str, Enum):
    """
    Classification of orchestration failure modes.
    
    Used to distinguish between different types of errors during agent execution.
    """
    
    # Timeout failures
    TODO_PLAN_TIMEOUT = "todo_plan_timeout"  # Planning phase for a TODO exceeded timeout
    TODO_STEP_TIMEOUT = "todo_step_timeout"  # Step execution within a TODO exceeded timeout
    RUN_TIMEOUT = "run_timeout"              # Entire orchestration run exceeded timeout
    
    # Execution failures
    ORCHESTRATOR_ERROR = "orchestrator_error"  # General orchestrator execution error
    LLM_ERROR = "llm_error"                    # LLM call failed or returned error
    TOOL_ERROR = "tool_error"                  # Tool execution failed
    VALIDATION_ERROR = "validation_error"      # Input/output validation failed
    
    # Resource failures
    RESOURCE_EXHAUSTED = "resource_exhausted"  # System resources exhausted
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"  # Rate limit hit
    
    # Cancellation
    USER_CANCELLED = "user_cancelled"          # User explicitly cancelled the run


def get_failure_message(failure_type: FailureType, **context) -> str:
    """
    Get human-readable error message for a failure type.
    
    Args:
        failure_type: The type of failure that occurred
        **context: Additional context (e.g., timeout_seconds, todo_index)
    
    Returns:
        Human-readable error message
    """
    messages = {
        FailureType.TODO_PLAN_TIMEOUT: "Planning timeout for TODO #{todo_index}: Exceeded {timeout_seconds}s while generating plan",
        FailureType.TODO_STEP_TIMEOUT: "Step execution timeout: {step_action} exceeded {timeout_seconds}s",
        FailureType.RUN_TIMEOUT: "Orchestration timeout: Run exceeded {timeout_seconds}s",
        FailureType.ORCHESTRATOR_ERROR: "Orchestrator execution failed: {error_detail}",
        FailureType.LLM_ERROR: "LLM call failed: {error_detail}",
        FailureType.TOOL_ERROR: "Tool execution failed: {tool_name} - {error_detail}",
        FailureType.VALIDATION_ERROR: "Validation error: {error_detail}",
        FailureType.RESOURCE_EXHAUSTED: "Resource exhausted: {resource_type}",
        FailureType.RATE_LIMIT_EXCEEDED: "Rate limit exceeded: {limit_type}",
        FailureType.USER_CANCELLED: "Run cancelled by user",
    }
    
    template = messages.get(failure_type, "Unknown failure: {error_detail}")
    return template.format(**context)
