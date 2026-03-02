"""
Agent-specific Prometheus metrics for the Cineca Agentic Platform.

This module extends the base metrics with agent orchestration-specific
instrumentation including:
- Agent run counters and latency histograms (per agent, status, tenant)
- Tool invocation metrics within agent context
- LLM call metrics (model, tokens, errors)
- Agent error tracking by type and phase
- Queue depth and concurrency gauges

All metrics follow the Prometheus best practices and are designed
to support SLOs and alerting rules for agent operations.
"""

from __future__ import annotations

import structlog
from fastapi import FastAPI
from prometheus_client import Counter, Gauge, Histogram

log = structlog.get_logger(__name__)


class AgentMetrics:
    """
    Agent-specific Prometheus metrics bundled into a single class.
    Attached to FastAPI app.state during setup.
    """

    def __init__(self, registry) -> None:
        # ── Agent Run Metrics ────────────────────────────────────────────
        self.agent_runs_total = Counter(
            "agent_runs_total",
            "Total number of agent runs initiated.",
            ["agent_type", "status", "tenant_id"],
            registry=registry,
        )

        self.agent_run_duration_seconds = Histogram(
            "agent_run_duration_seconds",
            "Agent run duration in seconds (end-to-end).",
            ["agent_type", "status"],
            buckets=(0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0),
            registry=registry,
        )

        self.agent_active_runs = Gauge(
            "agent_active_runs",
            "Number of currently active agent runs.",
            ["agent_type", "tenant_id"],
            registry=registry,
        )

        # ── Agent Phase Metrics ──────────────────────────────────────────
        self.agent_phase_duration_seconds = Histogram(
            "agent_phase_duration_seconds",
            "Duration of individual agent phases (planning, execution, etc.).",
            ["agent_type", "phase"],
            buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
            registry=registry,
        )

        # ── LLM Call Metrics ─────────────────────────────────────────────
        self.llm_calls_total = Counter(
            "llm_calls_total",
            "Total number of LLM API calls made by agents.",
            ["model", "provider", "status"],
            registry=registry,
        )

        self.llm_call_duration_seconds = Histogram(
            "llm_call_duration_seconds",
            "LLM API call duration in seconds.",
            ["model", "provider", "status"],
            buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
            registry=registry,
        )

        self.llm_tokens_total = Counter(
            "llm_tokens_total",
            "Total number of tokens consumed by LLM calls.",
            ["model", "provider", "type"],  # type: prompt/completion/total
            registry=registry,
        )

        self.llm_errors_total = Counter(
            "llm_errors_total",
            "Total number of LLM API errors.",
            ["model", "provider", "error_type"],
            registry=registry,
        )

        # ── Tool Invocation Metrics (Agent Context) ──────────────────────
        self.agent_tool_calls_total = Counter(
            "agent_tool_calls_total",
            "Total number of tool calls made within agent runs.",
            ["agent_type", "tool_name", "status"],
            registry=registry,
        )

        self.agent_tool_call_duration_seconds = Histogram(
            "agent_tool_call_duration_seconds",
            "Tool call duration within agent context.",
            ["tool_name", "status"],
            buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
            registry=registry,
        )

        # ── Error Tracking ───────────────────────────────────────────────
        self.agent_errors_total = Counter(
            "agent_errors_total",
            "Total number of errors during agent execution.",
            ["agent_type", "error_type", "phase"],
            registry=registry,
        )

        self.agent_retries_total = Counter(
            "agent_retries_total",
            "Total number of retry attempts.",
            ["agent_type", "reason"],
            registry=registry,
        )

        # ── Queue & Concurrency ──────────────────────────────────────────
        self.agent_queue_depth = Gauge(
            "agent_queue_depth",
            "Current depth of agent execution queue.",
            ["priority"],  # high/normal/low
            registry=registry,
        )

        self.agent_concurrency_limit = Gauge(
            "agent_concurrency_limit",
            "Maximum allowed concurrent agent runs.",
            ["tenant_id"],
            registry=registry,
        )

        self.agent_concurrency_throttled_total = Counter(
            "agent_concurrency_throttled_total",
            "Number of times agent runs were throttled due to concurrency limits.",
            ["tenant_id"],
            registry=registry,
        )

        # ── Orchestrator Metrics ─────────────────────────────────────────
        self.orchestrator_steps_total = Counter(
            "orchestrator_steps_total",
            "Total number of orchestrator steps executed.",
            ["agent_type", "step_type"],
            registry=registry,
        )

        self.orchestrator_step_duration_seconds = Histogram(
            "orchestrator_step_duration_seconds",
            "Duration of individual orchestrator steps.",
            ["step_type"],
            buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
            registry=registry,
        )


# ──────────────────────────────────────────────────────────────────────────────
# Setup & Helper Functions
# ──────────────────────────────────────────────────────────────────────────────


def setup_agent_metrics(app: FastAPI) -> None:
    """
    Initialize agent-specific metrics for the provided FastAPI app.
    Requires that setup_metrics() from observability.metrics has already been called.
    """
    registry = getattr(app.state, "prometheus_registry", None)
    if registry is None:
        log.warning("observability.agent_metrics.no_registry_found")
        return

    if getattr(app.state, "agent_metrics", None) is not None:
        log.debug("observability.agent_metrics.already_configured")
        return

    agent_metrics = AgentMetrics(registry=registry)
    app.state.agent_metrics = agent_metrics
    log.info("observability.agent_metrics.configured")


def get_agent_metrics(app: FastAPI | None = None) -> AgentMetrics | None:
    """
    Retrieve the AgentMetrics instance from the provided app or from the most
    recent configured app.
    """
    if app is not None:
        return getattr(app.state, "agent_metrics", None)

    return globals().get("_last_agent_metrics")  # type: ignore


def _remember_agent_metrics(metrics: AgentMetrics) -> None:
    globals()["_last_agent_metrics"] = metrics


# Patch setup to remember metrics
_orig_setup = setup_agent_metrics


def setup_agent_metrics(app: FastAPI) -> None:  # type: ignore[no-redef]
    _orig_setup(app)
    metrics = getattr(app.state, "agent_metrics", None)
    if isinstance(metrics, AgentMetrics):
        _remember_agent_metrics(metrics)


# ──────────────────────────────────────────────────────────────────────────────
# Recording Helper Functions
# ──────────────────────────────────────────────────────────────────────────────


def record_agent_run_start(
    agent_type: str,
    tenant_id: str = "default",
    app: FastAPI | None = None,
) -> None:
    """Increment active agent runs gauge."""
    metrics = get_agent_metrics(app)
    if not metrics:
        return
    try:
        metrics.agent_active_runs.labels(agent_type, tenant_id).inc()
    except Exception as e:
        log.warning("observability.agent_metrics.record_start_failed", error=str(e))


def record_agent_run_complete(
    agent_type: str,
    status: str,
    duration_seconds: float,
    tenant_id: str = "default",
    app: FastAPI | None = None,
) -> None:
    """Record agent run completion with status and duration."""
    metrics = get_agent_metrics(app)
    if not metrics:
        return
    try:
        metrics.agent_runs_total.labels(agent_type, status, tenant_id).inc()
        metrics.agent_run_duration_seconds.labels(agent_type, status).observe(duration_seconds)
        metrics.agent_active_runs.labels(agent_type, tenant_id).dec()
    except Exception as e:
        log.warning("observability.agent_metrics.record_complete_failed", error=str(e))


def record_agent_phase(
    agent_type: str,
    phase: str,
    duration_seconds: float,
    app: FastAPI | None = None,
) -> None:
    """Record duration of an agent execution phase."""
    metrics = get_agent_metrics(app)
    if not metrics:
        return
    try:
        metrics.agent_phase_duration_seconds.labels(agent_type, phase).observe(duration_seconds)
    except Exception as e:
        log.warning("observability.agent_metrics.record_phase_failed", error=str(e))


def record_llm_call(
    model: str,
    provider: str,
    status: str,
    duration_seconds: float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    app: FastAPI | None = None,
) -> None:
    """Record LLM API call metrics."""
    metrics = get_agent_metrics(app)
    if not metrics:
        return
    try:
        metrics.llm_calls_total.labels(model, provider, status).inc()
        metrics.llm_call_duration_seconds.labels(model, provider, status).observe(duration_seconds)
        if prompt_tokens > 0:
            metrics.llm_tokens_total.labels(model, provider, "prompt").inc(prompt_tokens)
        if completion_tokens > 0:
            metrics.llm_tokens_total.labels(model, provider, "completion").inc(completion_tokens)
        if prompt_tokens > 0 or completion_tokens > 0:
            metrics.llm_tokens_total.labels(model, provider, "total").inc(prompt_tokens + completion_tokens)
    except Exception as e:
        log.warning("observability.agent_metrics.record_llm_call_failed", error=str(e))


def record_llm_error(
    model: str,
    provider: str,
    error_type: str,
    app: FastAPI | None = None,
) -> None:
    """Record LLM API error."""
    metrics = get_agent_metrics(app)
    if not metrics:
        return
    try:
        metrics.llm_errors_total.labels(model, provider, error_type).inc()
    except Exception as e:
        log.warning("observability.agent_metrics.record_llm_error_failed", error=str(e))


def record_agent_tool_call(
    agent_type: str,
    tool_name: str,
    status: str,
    duration_seconds: float,
    app: FastAPI | None = None,
) -> None:
    """Record tool call within agent context."""
    metrics = get_agent_metrics(app)
    if not metrics:
        return
    try:
        metrics.agent_tool_calls_total.labels(agent_type, tool_name, status).inc()
        metrics.agent_tool_call_duration_seconds.labels(tool_name, status).observe(duration_seconds)
    except Exception as e:
        log.warning("observability.agent_metrics.record_tool_call_failed", error=str(e))


def record_agent_error(
    agent_type: str,
    error_type: str,
    phase: str,
    app: FastAPI | None = None,
) -> None:
    """Record agent execution error."""
    metrics = get_agent_metrics(app)
    if not metrics:
        return
    try:
        metrics.agent_errors_total.labels(agent_type, error_type, phase).inc()
    except Exception as e:
        log.warning("observability.agent_metrics.record_error_failed", error=str(e))


def record_orchestrator_step(
    agent_type: str,
    step_type: str,
    duration_seconds: float,
    app: FastAPI | None = None,
) -> None:
    """Record orchestrator step execution."""
    metrics = get_agent_metrics(app)
    if not metrics:
        return
    try:
        metrics.orchestrator_steps_total.labels(agent_type, step_type).inc()
        metrics.orchestrator_step_duration_seconds.labels(step_type).observe(duration_seconds)
    except Exception as e:
        log.warning("observability.agent_metrics.record_step_failed", error=str(e))


__all__ = [
    "AgentMetrics",
    "get_agent_metrics",
    "record_agent_error",
    "record_agent_phase",
    "record_agent_run_complete",
    "record_agent_run_start",
    "record_agent_tool_call",
    "record_llm_call",
    "record_llm_error",
    "record_orchestrator_step",
    "setup_agent_metrics",
]
