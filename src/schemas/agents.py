"""Pydantic schemas for agent API endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.utils.run_output import normalize_run_output

# ============ Session Schemas ============


class CreateSessionRequest(BaseModel):
    """Request to create a new agent session."""

    session_id: UUID | None = Field(
        default=None,
        description="Optional client-provided session ID. If provided and owned by caller, returns existing session idempotently.",
    )
    prompt: str | None = Field(default=None, description="Optional natural-language input for the agent to act on")
    manager: str | None = Field(
        default=None, description="Optional named manager/planner LLM to use (e.g., 'planner')"
    )
    preferred_workers: list[str] | None = Field(
        default=None, description="Optional allowlist of worker LLM names the manager may use"
    )
    llm_preferences: dict[str, str] | None = Field(
        default=None, description="Optional per-session mapping of tool/action -> preferred LLM name"
    )
    agent_role: str | None = Field(
        default=None, description="Optional agent role (e.g., 'researcher','coder') to influence system prompt"
    )
    tools: list[str] | None = Field(default=None, description="Optional allowlist of tool names the agent may use")
    temperature: float = Field(
        0.2, ge=0.0, le=2.0, description="Sampling temperature for stochastic models (0.0 = deterministic)"
    )
    max_steps: int = Field(8, ge=1, le=64, description="Maximum planner/agent steps to execute")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata passed to the orchestrator")


class SessionResponse(BaseModel):
    """Response containing session details."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    session_id: UUID = Field(..., description="Session identifier")
    user_id: str = Field(..., description="Owner user ID")
    tenant_id: str = Field(..., description="Tenant ID")
    status: str = Field(..., description="Session status (active, completed, cancelled, failed)")
    manager: str | None = Field(None, description="Manager/planner LLM name if configured")
    preferred_workers: list[str] | None = Field(None, description="Preferred worker LLM names")
    llm_preferences: dict[str, str] | None = Field(None, description="Tool -> LLM preferences")
    agent_role: str | None = Field(None, description="Agent role")
    tools: list[str] | None = Field(None, description="Allowed tools")
    temperature: float = Field(..., description="Sampling temperature")
    max_steps: int = Field(..., description="Maximum steps")
    metadata: dict[str, Any] = Field(..., alias="session_metadata", description="Session metadata")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    last_step_id: UUID | None = Field(None, description="ID of the last step in this session")
    etag: str | None = Field(None, description="ETag for caching")


class SessionListItem(BaseModel):
    """Minimal session info for list responses."""

    session_id: UUID = Field(..., description="Session identifier")
    status: str = Field(..., description="Session status")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    last_step_seq: int | None = Field(None, description="Sequence number of last step")
    manager: str | None = Field(None, description="Manager name if configured")


class SessionListResponse(BaseModel):
    """Paginated list of sessions."""

    items: list[SessionListItem] = Field(default_factory=list, description="Session items")
    next_cursor: str | None = Field(None, description="Opaque cursor for next page")


# ============ Step Schemas ============


class CreateStepRequest(BaseModel):
    """Request to add a step to a session."""

    type: str = Field(
        ...,
        description="Step type: 'message' (user message), 'user' (user action), 'assistant' (LLM response), 'tool' (tool invocation), 'system' (system message), 'error' (error occurred)",
        examples=["message"],
    )
    message: str | None = Field(None, description="Human-readable message")
    tool: str | None = Field(None, description="Tool name if this is a tool step")
    input: dict[str, Any] | None = Field(None, description="Structured input payload")
    output: dict[str, Any] | None = Field(None, description="Structured output payload")

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        allowed = {"message", "user", "assistant", "tool", "system", "error"}
        if v not in allowed:
            raise ValueError(f"type must be one of {allowed}")
        return v


class StepResponse(BaseModel):
    """Response containing step details from database."""

    model_config = ConfigDict(from_attributes=True)

    step_id: UUID = Field(..., description="Step identifier")
    session_id: UUID = Field(..., description="Session identifier")
    seq: int = Field(..., description="Sequence number within session")
    type: str = Field(..., description="Step type")
    message: str | None = Field(None, description="Human-readable message")
    tool: str | None = Field(None, description="Tool name")
    input: dict[str, Any] | None = Field(None, description="Input payload")
    output: dict[str, Any] | None = Field(None, description="Output payload")
    status: str = Field(..., description="Step status (queued, running, completed, failed, cancelled)")
    error: dict[str, Any] | None = Field(None, description="Error details if failed")
    created_at: datetime = Field(..., description="Creation timestamp")
    completed_at: datetime | None = Field(None, description="Completion timestamp")


class StepListResponse(BaseModel):
    """Paginated list of steps."""

    items: list[StepResponse] = Field(default_factory=list, description="Step items")
    next_cursor: str | None = Field(None, description="Opaque cursor for next page")


# ============ Run Schemas ============


class OrchestrationStepInput(BaseModel):
    """Represents a planned orchestration step."""

    model_config = ConfigDict(extra="allow")

    type: Literal["step"] = "step"
    step_id: str = Field(..., description="Step identifier (can be string like '1', '2', 'create-todos')")
    action: str = Field(..., description="Action/tool to execute")
    input: dict[str, Any] | None = Field(None, description="Input parameters for the action")
    started_at: datetime | None = Field(None, description="ISO timestamp when step execution started")
    finished_at: datetime | None = Field(None, description="ISO timestamp when step execution finished")
    latency_ms: int | None = Field(None, description="Execution latency in milliseconds")
    
    @model_validator(mode='after')
    def calculate_latency(self) -> 'OrchestrationStepInput':
        """
        Calculate latency_ms from timestamps if missing (Issue #6).
        
        Ensures timing consistency:
        - If started_at and finished_at present but latency_ms missing, calculate it
        - If latency_ms present but inconsistent with timestamps, log warning
        """
        if self.started_at and self.finished_at:
            calculated_ms = int((self.finished_at - self.started_at).total_seconds() * 1000)
            
            if self.latency_ms is None:
                # Calculate missing latency
                self.latency_ms = calculated_ms
            elif abs(self.latency_ms - calculated_ms) > 10:  # Allow 10ms tolerance
                # Log warning if inconsistent
                import structlog
                log = structlog.get_logger(__name__)
                log.warning(
                    "step.latency.inconsistent",
                    step_id=self.step_id,
                    stored_ms=self.latency_ms,
                    calculated_ms=calculated_ms,
                    diff_ms=abs(self.latency_ms - calculated_ms)
                )
        
        return self


class OrchestrationStepOutput(BaseModel):
    """Represents output from an executed orchestration step."""

    model_config = ConfigDict(extra="allow")

    type: Literal["output"] = "output"
    step_id: str = Field(..., description="Step identifier matching the input step")
    output: dict[str, Any] | None = Field(None, description="Output data from step execution")
    error: str | None = Field(None, description="Error message if step failed")
    started_at: datetime | None = Field(None, description="ISO timestamp when step execution started")
    finished_at: datetime | None = Field(None, description="ISO timestamp when step execution finished")
    latency_ms: int | None = Field(None, description="Execution latency in milliseconds")
    
    @model_validator(mode='after')
    def calculate_latency(self) -> 'OrchestrationStepOutput':
        """
        Calculate latency_ms from timestamps if missing (Issue #6).
        
        Ensures timing consistency:
        - If started_at and finished_at present but latency_ms missing, calculate it
        - If latency_ms present but inconsistent with timestamps, log warning
        """
        if self.started_at and self.finished_at:
            calculated_ms = int((self.finished_at - self.started_at).total_seconds() * 1000)
            
            if self.latency_ms is None:
                # Calculate missing latency
                self.latency_ms = calculated_ms
            elif abs(self.latency_ms - calculated_ms) > 10:  # Allow 10ms tolerance
                # Log warning if inconsistent
                import structlog
                log = structlog.get_logger(__name__)
                log.warning(
                    "step.latency.inconsistent",
                    step_id=self.step_id,
                    stored_ms=self.latency_ms,
                    calculated_ms=calculated_ms,
                    diff_ms=abs(self.latency_ms - calculated_ms)
                )
        
        return self


class TodoItem(BaseModel):
    """Represents a TODO task in the agent's plan."""

    task: str = Field(..., description="Description of the task to complete")
    status: Literal["pending", "in_progress", "completed", "failed"] | None = Field(
        None, description="Current status of the TODO item"
    )
    expect_evidence: bool = Field(
        default=True,
        description="Whether this TODO is expected to produce external evidence (skip warnings when False)",
    )
    evidence: list[str] = Field(
        default_factory=list,
        description="Optional evidence entries (step ids, actions, or summaries) that support completion",
    )
    meta: dict[str, Any] | None = Field(
        default_factory=dict,
        description="Optional metadata to guide execution (tool hints, modes, prompt ids)",
    )
    requires_llm_planning: bool = Field(
        default=True,
        description="When false, the orchestrator should execute this TODO directly without LLM planning",
    )
    nested_steps: list[str] = Field(
        default_factory=list,
        description="Nested step descriptions (e.g., from LLM JSON with step_description fields) for tool validation",
    )
    fallback_mode: bool = Field(
        default=False,
        description="When true, this TODO is expected to complete without tools (fallback/LLM-only mode)",
    )


class LLMCallMetrics(BaseModel):
    """Metrics for a single LLM API call."""

    model: str = Field(..., description="Model name used for this call")
    latency_ms: int = Field(..., description="Latency in milliseconds")
    success: bool = Field(..., description="Whether the call succeeded")
    input_tokens: int | None = Field(None, description="Number of input tokens")
    output_tokens: int | None = Field(None, description="Number of output tokens")
    total_tokens: int | None = Field(None, description="Total number of tokens (input + output)")
    purpose: str | None = Field(None, description="Purpose of the call (e.g., 'todo_list_creation')")
    error: str | None = Field(None, description="Error message if call failed")
    
    @model_validator(mode='after')
    def calculate_total_tokens(self) -> 'LLMCallMetrics':
        """
        Calculate total_tokens from input/output if missing (Issue #1).
        
        Ensures token counts are always complete:
        - If total_tokens null but input/output present, calculate sum
        - Defaults to 0 if all fields null (better than null for aggregation)
        """
        if self.total_tokens is None:
            if self.input_tokens is not None and self.output_tokens is not None:
                # Calculate from components
                self.total_tokens = self.input_tokens + self.output_tokens
            elif self.input_tokens is not None:
                # Only input available
                self.total_tokens = self.input_tokens
            elif self.output_tokens is not None:
                # Only output available
                self.total_tokens = self.output_tokens
            else:
                # No token data available - default to 0 for aggregation
                self.total_tokens = 0
        
        # Also default input/output to 0 if null (consistent with total)
        if self.input_tokens is None:
            self.input_tokens = 0
        if self.output_tokens is None:
            self.output_tokens = 0
        
        return self


class ToolCallMetrics(BaseModel):
    """Metrics for a single tool invocation."""

    name: str = Field(..., description="Tool name")
    latency_ms: int = Field(..., description="Execution latency in milliseconds")
    success: bool = Field(..., description="Whether the tool call succeeded")


class ExecutionMetrics(BaseModel):
    """Performance and execution metrics for the run."""

    overall_ms: int = Field(..., description="Overall execution time in milliseconds")
    llm: list[LLMCallMetrics] = Field(default_factory=list, description="LLM call metrics")
    tools: list[ToolCallMetrics] = Field(default_factory=list, description="Tool call metrics")
    
    # Legacy fields for backward compatibility
    model_warmup_ms: int | None = Field(None, description="Time taken for model warmup in milliseconds")
    first_llm_call_ms: int | None = Field(
        None,
        description="Latency of the first LLM call within this run (preferred over model_warmup_ms for clarity)",
    )
    # Removed unused fields: todo_creation_ms, todo_execution_ms (never populated)
    total_llm_calls: int | None = Field(None, description="Total number of LLM API calls made")
    llm_call_count: int | None = Field(None, description="Number of LLM calls made during this run (excludes warmup)")
    llm_attempted_calls: int | None = Field(None, description="Number of LLM calls attempted (including failures)")
    llm_successful_calls: int | None = Field(None, description="Number of LLM calls that succeeded")
    tool_calls: int | None = Field(None, description="Total number of tool invocations")
    tool_errors: int | None = Field(None, description="Number of tool invocation errors")
    timeout_stage: str | None = Field(None, description="Stage where timeout occurred (if applicable)")
    
    # Configuration/budget metrics (for SRE dashboards)
    configured_run_timeout_seconds: int | None = Field(None, description="Configured run timeout (seconds)")
    configured_step_timeout_seconds: int | None = Field(None, description="Configured step timeout (seconds)")
    run_timeout_budget_ms: int | None = Field(None, description="Remaining timeout budget at run end (ms)")
    planning_ms: int | None = Field(None, description="Time spent in planning phase (ms)")
    execution_ms: int | None = Field(None, description="Time spent in execution phase (ms)")
    
    # Error details (for debugging/alerting)
    timeout_reason: str | None = Field(None, description="Reason for timeout if applicable")
    llm_error_type: str | None = Field(None, description="Type of LLM error if any (e.g., TimeoutException)")
    llm_error_message: str | None = Field(None, description="LLM error message if any")
    llm_latency: dict[str, Any] | None = Field(
        None,
        description="Aggregate LLM latency breakdown: {per_purpose: {<purpose>: {avg_ms, p95_ms, count}}, slow_calls: {gt_60s, gt_120s}}"
    )


class CreateRunRequest(BaseModel):
    """Request to create a new agent run."""

    session_id: UUID | None = Field(
        default=None, description="Optional session ID. If not provided, a new session will be created."
    )
    prompt: str = Field(..., description="Natural-language input for the agent to act on")
    manager: str | None = Field(default=None, description="Manager/planner LLM name")
    preferred_workers: list[str] | None = Field(default=None, description="Preferred workers")
    llm_preferences: dict[str, str] | None = Field(default=None, description="Tool preferences")
    agent_role: str | None = Field(default=None, description="Agent role")
    tools: list[str] | None = Field(default=None, description="Allowed tools")
    temperature: float = Field(0.2, ge=0.0, le=2.0, description="Sampling temperature")
    max_steps: int = Field(8, ge=1, le=64, description="Maximum steps")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Metadata")
    force_full_agentic: bool = Field(
        default=False,
        description="Force full agentic pipeline (disable trivial fast paths)",
    )


class RunResponse(BaseModel):
    """Response containing run details with properly typed orchestration artifacts."""

    model_config = ConfigDict(from_attributes=True)

    run_id: UUID = Field(..., description="Run identifier")
    session_id: UUID | None = Field(None, description="Associated session ID")
    user_id: str = Field(..., description="Owner user ID")
    tenant_id: str = Field(..., description="Tenant ID")
    
    @field_validator('tenant_id', mode='before')
    @classmethod
    def validate_tenant_id(cls, v: str) -> str:
        """
        Ensure tenant_id is never empty (Issue #9).
        
        Validates that tenant_id is present and non-empty.
        Provides better error message than generic "field required".
        """
        if not v or (isinstance(v, str) and v.strip() == ""):
            raise ValueError("tenant_id must be non-empty string")
        return v
    
    model: str | None = Field(None, description="Model name used")
    manager: str | None = Field(None, description="Manager name used")
    
    @field_validator('model', mode='before')
    @classmethod
    def normalize_model_name(cls, v: str | None) -> str | None:
        """
        Normalize model names to consistent format (Issue #2).
        
        Converts kebab-case model names to colon-separated format:
        - phi3-mini -> phi3:mini
        - llama3-8b -> llama3:8b
        - gpt-4 -> gpt-4 (OpenAI models stay as-is)
        
        Only normalizes if pattern matches <model><dash><variant>.
        """
        if not v:
            return v
        
        # Common Ollama models that use colon format
        ollama_patterns = ['phi3', 'llama3', 'llama2', 'mistral', 'codellama']
        
        # Check if model matches <base>-<variant> pattern
        for pattern in ollama_patterns:
            if v.startswith(pattern) and '-' in v:
                # Replace first dash with colon
                parts = v.split('-', 1)
                normalized = f"{parts[0]}:{parts[1]}"
                return normalized
        
        # Return as-is if no normalization needed
        return v
    latency_ms: int | None = Field(None, description="Run latency in milliseconds")
    trace_id: str | None = Field(None, description="Stable provenance trace ID (persists across requests)")
    request_id: str | None = Field(None, description="HTTP request ID (matches X-Request-Id header)")
    event_id: str | None = Field(None, description="Provenance event ID")
    status: str = Field(..., description="Run status (running, succeeded, failed, cancelled)")
    started_at: datetime = Field(..., description="Start timestamp")
    finished_at: datetime | None = Field(None, description="Finish timestamp")
    output: dict | list | None = Field(None, description="Run output (structured object or list, never empty string)")
    steps: list[OrchestrationStepInput | OrchestrationStepOutput] | None = Field(
        None, description="Orchestration steps from execution (inputs and outputs)"
    )
    todos: list[TodoItem] | None = Field(None, description="TODO list generated by agent")
    metrics: ExecutionMetrics | None = Field(None, description="Execution performance metrics")
    metadata: dict[str, Any] | None = Field(default_factory=dict, description="Arbitrary metadata provided with the run request")
    errors: list[str] | None = Field(None, description="List of errors encountered during execution")
    warnings: list[str] | None = Field(None, description="List of non-fatal warnings encountered during execution")
    
    # Degraded/fallback indicator for observability
    degraded: bool | None = Field(
        None,
        description=(
            "True if run succeeded but with degraded quality (e.g., LLM fallback used). "
            "Allows dashboards to distinguish clean success from fallback-success."
        )
    )
    used_fallback: bool | None = Field(
        None,
        description=(
            "True if deterministic fallback was used instead of LLM response. "
            "Specifically indicates memgraph_response_builder or similar fallback paths."
        )
    )
    
    # Rollup metrics fields for backwards compatibility (also in metrics.*)
    # Note: model_warmup_ms removed from root - only in metrics.model_warmup_ms (Issue #5)
    total_llm_calls: int | None = Field(None, description="Total number of LLM calls made (rollup)")
    llm_call_count: int | None = Field(None, description="Number of LLM calls made during this run (excludes warmup)")
    tool_calls: int | None = Field(None, description="Total number of tool calls made (rollup)")
    tool_errors: int | None = Field(None, description="Total number of tool errors encountered (rollup)")

    @field_validator('output', mode='before')
    @classmethod
    def normalize_output_field(cls, v):
        """Ensure output always matches schema contract (dict/list/None)."""
        if v == "":
            return None
        return normalize_run_output(v)

    @model_validator(mode='after')
    def extract_rollup_metrics(self) -> 'RunResponse':
        """
        Extract/calculate rollup metrics from metrics object (Issue #7).
        
        If rollup fields (total_llm_calls, llm_call_count, tool_calls, tool_errors) are null,
        calculate them from the llm and tools lists in metrics.
        Note: model_warmup_ms now only in metrics.model_warmup_ms (Issue #5).
        """
        if self.metrics:
            # Extract from ExecutionMetrics if already set
            if self.total_llm_calls is None and hasattr(self.metrics, 'total_llm_calls'):
                self.total_llm_calls = self.metrics.total_llm_calls
            if self.llm_call_count is None and hasattr(self.metrics, 'llm_call_count'):
                self.llm_call_count = self.metrics.llm_call_count
            if self.tool_calls is None and hasattr(self.metrics, 'tool_calls'):
                self.tool_calls = self.metrics.tool_calls
            if self.tool_errors is None and hasattr(self.metrics, 'tool_errors'):
                self.tool_errors = self.metrics.tool_errors
            
            # Calculate from llm/tools lists if still null (Issue #7)
            if self.total_llm_calls is None and hasattr(self.metrics, 'llm'):
                self.total_llm_calls = len(self.metrics.llm) if self.metrics.llm else 0
            
            if self.tool_calls is None and hasattr(self.metrics, 'tools'):
                self.tool_calls = len(self.metrics.tools) if self.metrics.tools else 0
            
            if self.tool_errors is None and hasattr(self.metrics, 'tools'):
                # Count tools with success=False (Issue #7)
                self.tool_errors = sum(
                    1 for tool in (self.metrics.tools or [])
                    if hasattr(tool, 'success') and not tool.success
                ) if self.metrics.tools else 0
        
        return self
    
    @model_validator(mode='after')
    def validate_output_type(self) -> 'RunResponse':
        """Ensure output consistency and log warnings for edge cases."""
        # If status is succeeded, output should ideally be populated
        if self.status == "succeeded" and self.output is None:
            # Log warning but don't fail - might be legitimate edge case
            import structlog
            log = structlog.get_logger()
            log.warning("run.output.empty_on_success", run_id=str(self.run_id), status=self.status)
        return self


    # Track todos already warned for missing evidence to prevent duplicate logs
    _WARNED_TODO_EVIDENCE: ClassVar[set[tuple[str, str]]] = set()
    
    # Common tool names to look for in todo text and nested steps
    _KNOWN_TOOL_NAMES: ClassVar[tuple[str, ...]] = (
        "graph.generate_cypher",
        "graph.secure_query", 
        "graph.query",
        "graph.crud",
        "graph.schema",
        "graph.search",
        "graph.analytics",
        "graph.bulk",
        "data.archive",
        "data.quality",
        "cache.manage",
        "model.manage",
        "output.format",
        "output.summarize",
    )

    @staticmethod
    def _extract_tool_mentions(text: str, known_tools: tuple[str, ...]) -> list[str]:
        """Extract tool names mentioned in the given text."""
        text_lower = text.lower()
        return [tool for tool in known_tools if tool.lower() in text_lower]

    @model_validator(mode='after')
    def validate_todo_completion_evidence(self) -> 'RunResponse':
        """
        Validate that completed TODOs have evidence in steps (Issue #8).
        
        Ensures integrity: If a TODO is marked "completed", there should be
        at least one execution step that could reasonably complete it.
        
        Enhanced to:
        - Scan nested_steps for tool mentions (not just main task text)
        - Respect fallback_mode flag to downgrade warnings to INFO
        - Handle both legacy string lists and structured JSON todo formats
        
        Logs warning (doesn't fail) to avoid breaking existing data.
        """
        if not self.todos or not self.steps:
            return self
        
        import structlog
        log = structlog.get_logger()
        
        # Build quick lookup of steps by todo index (todo-X prefix or explicit todo_index/meta)
        steps_by_idx: dict[int, list[Any]] = {}
        executed_tools: set[str] = set()
        for step in self.steps:
            todo_index = None
            step_id = getattr(step, "step_id", None) or getattr(step, "id", None)
            action_val = getattr(step, "action", "") or ""
            if action_val:
                executed_tools.add(action_val.lower())
            if hasattr(step, "todo_index"):
                todo_index = getattr(step, "todo_index")
            elif hasattr(step, "meta") and isinstance(step.meta, dict):
                todo_index = step.meta.get("todo_index")
            if todo_index is None and isinstance(step_id, str) and step_id.startswith("todo-"):
                maybe_idx = step_id.split("-", 2)[1]
                if maybe_idx.isdigit():
                    todo_index = int(maybe_idx)
            if isinstance(todo_index, int):
                steps_by_idx.setdefault(todo_index, []).append(step)
        
        for idx, todo in enumerate(self.todos):
            if todo.status != "completed":
                continue
            
            task_lower = todo.task.lower()
            expect_evidence = getattr(todo, "expect_evidence", True)
            fallback_mode = getattr(todo, "fallback_mode", False)
            nested_steps = getattr(todo, "nested_steps", []) or []
            todo_evidence = list(getattr(todo, "evidence", []) or [])

            # Collect all text to scan for tool mentions (main task + nested steps)
            all_todo_text = task_lower
            for nested in nested_steps:
                if isinstance(nested, str):
                    all_todo_text += " " + nested.lower()
            
            # Find which tools are mentioned in todo text or nested steps
            mentioned_tools = self._extract_tool_mentions(all_todo_text, self._KNOWN_TOOL_NAMES)

            # Structured evidence from steps tagged with todo_index
            if steps_by_idx.get(idx):
                todo_evidence.extend(
                    str(getattr(step, "action", None) or getattr(step, "step_id", "")) or ""
                    for step in steps_by_idx[idx]
                )

            # Heuristic evidence from matching step actions/ids
            if not todo_evidence and self.steps:
                for step in self.steps:
                    action_val = getattr(step, "action", "") or ""
                    step_id_val = getattr(step, "step_id", "") or ""
                    if action_val:
                        action_lower = action_val.lower()
                        # Check against main task AND nested steps
                        if action_lower in all_todo_text or any(
                            word in action_lower for word in all_todo_text.split() if len(word) > 3
                        ):
                            todo_evidence.append(action_val)
                            break
                    if step_id_val and step_id_val.lower() in all_todo_text:
                        todo_evidence.append(step_id_val)
                        break
            
            has_evidence = bool(todo_evidence)
            warning_key = (str(self.run_id), todo.task)
            
            # Check if mentioned tools were actually executed
            unexecuted_mentioned_tools = [
                tool for tool in mentioned_tools 
                if tool.lower() not in executed_tools
            ]

            # Determine if we should skip warning based on fallback_mode or expect_evidence
            should_skip_warning = fallback_mode or not expect_evidence
            
            if should_skip_warning and not has_evidence:
                # Fallback mode or summarization-only: INFO instead of warning
                if warning_key not in self.__class__._WARNED_TODO_EVIDENCE:
                    log.info(
                        "todo.completed_without_evidence.allowed",
                        run_id=str(self.run_id),
                        todo_task=todo.task,
                        todo_status=todo.status,
                        fallback_mode=fallback_mode,
                        mentioned_tools=mentioned_tools,
                    )
                    self.__class__._WARNED_TODO_EVIDENCE.add(warning_key)
                continue

            if not has_evidence and expect_evidence:
                if warning_key in self.__class__._WARNED_TODO_EVIDENCE:
                    continue
                log.warning(
                    "todo.completed_without_evidence",
                    run_id=str(self.run_id),
                    todo_task=todo.task,
                    todo_status=todo.status,
                    step_count=len(self.steps) if self.steps else 0,
                    mentioned_tools=mentioned_tools,
                    unexecuted_tools=unexecuted_mentioned_tools,
                    nested_steps_count=len(nested_steps),
                )
                self.__class__._WARNED_TODO_EVIDENCE.add(warning_key)
        
        return self

# ============ Error Schemas ============


class ProblemDetail(BaseModel):
    """RFC7807 problem detail for error responses."""

    type: str = Field(..., description="URI reference identifying the problem type")
    title: str = Field(..., description="Short human-readable summary")
    status: int = Field(..., description="HTTP status code")
    detail: str | None = Field(None, description="Human-readable explanation")
    instance: str | None = Field(None, description="URI reference to specific occurrence")
    extensions: dict[str, Any] | None = Field(None, description="Additional extension members")
