"""
Prometheus metrics for agent orchestration.

Tracks agent run performance, failure rates, and TODO execution metrics.
"""

from __future__ import annotations

try:
    from prometheus_client import Counter, Gauge, Histogram
    
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    # Mock implementations for when prometheus is not installed
    class Counter:
        def __init__(self, *args, **kwargs):
            pass
        def labels(self, *args, **kwargs):
            return self
        def inc(self, *args, **kwargs):
            pass
    
    class Histogram:
        def __init__(self, *args, **kwargs):
            pass
        def labels(self, *args, **kwargs):
            return self
        def observe(self, *args, **kwargs):
            pass
        def time(self):
            class _Timer:
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    pass
            return _Timer()
    
    class Gauge:
        def __init__(self, *args, **kwargs):
            pass
        def labels(self, *args, **kwargs):
            return self
        def set(self, *args, **kwargs):
            pass
        def inc(self, *args, **kwargs):
            pass
        def dec(self, *args, **kwargs):
            pass


# ──────────────────────────────────────────────────────────────────────────────
# Agent Run Metrics
# ──────────────────────────────────────────────────────────────────────────────

agent_run_duration_seconds = Histogram(
    'agent_run_duration_seconds',
    'Total duration of agent run execution',
    ['status', 'tenant_id'],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600]
)

agent_run_failures_total = Counter(
    'agent_run_failures_total',
    'Total agent run failures by type',
    ['failure_type', 'tenant_id']
)

agent_run_success_total = Counter(
    'agent_run_success_total',
    'Total successful agent runs',
    ['tenant_id']
)

agent_run_queued_total = Gauge(
    'agent_run_queued_total',
    'Number of agent runs currently queued',
    ['tenant_id']
)

agent_run_running_total = Gauge(
    'agent_run_running_total',
    'Number of agent runs currently running',
    ['tenant_id']
)

# ──────────────────────────────────────────────────────────────────────────────
# TODO Metrics
# ──────────────────────────────────────────────────────────────────────────────

agent_todos_count = Histogram(
    'agent_todos_count',
    'Number of TODOs generated per run',
    ['tenant_id'],
    buckets=[1, 2, 3, 5, 10, 20]
)

agent_todo_duration_seconds = Histogram(
    'agent_todo_duration_seconds',
    'Duration per TODO execution',
    ['status', 'tenant_id'],
    buckets=[1, 5, 10, 30, 60, 120]
)

agent_todo_failures_total = Counter(
    'agent_todo_failures_total',
    'Total TODO failures by type',
    ['failure_type', 'tenant_id']
)

# ──────────────────────────────────────────────────────────────────────────────
# Step Metrics
# ──────────────────────────────────────────────────────────────────────────────

agent_step_duration_seconds = Histogram(
    'agent_step_duration_seconds',
    'Duration per step execution',
    ['action', 'status', 'tenant_id'],
    buckets=[0.1, 0.5, 1, 5, 10, 30, 60, 120]
)

agent_step_failures_total = Counter(
    'agent_step_failures_total',
    'Total step execution failures',
    ['action', 'tenant_id']
)

# ──────────────────────────────────────────────────────────────────────────────
# LLM Metrics
# ──────────────────────────────────────────────────────────────────────────────

agent_llm_calls_total = Counter(
    'agent_llm_calls_total',
    'Total LLM calls made by orchestrator',
    ['model', 'status', 'tenant_id']
)

agent_llm_duration_seconds = Histogram(
    'agent_llm_duration_seconds',
    'Duration of LLM calls',
    ['model', 'tenant_id'],
    buckets=[0.5, 1, 2, 5, 10, 30, 60, 120]
)

agent_llm_tokens_total = Counter(
    'agent_llm_tokens_total',
    'Total tokens consumed by LLM calls',
    ['model', 'token_type', 'tenant_id']
)

# ──────────────────────────────────────────────────────────────────────────────
# Model Warmup Metrics
# ──────────────────────────────────────────────────────────────────────────────

model_warmup_duration_seconds = Histogram(
    'model_warmup_duration_seconds',
    'Duration of model warmup',
    ['model', 'provider'],
    buckets=[1, 5, 10, 30, 60, 120, 300]
)

model_warmup_success_total = Counter(
    'model_warmup_success_total',
    'Total successful model warmups',
    ['model', 'provider']
)

model_warmup_failure_total = Counter(
    'model_warmup_failure_total',
    'Total failed model warmups',
    ['model', 'provider']
)

# ──────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ──────────────────────────────────────────────────────────────────────────────

def record_run_duration(duration_seconds: float, status: str, tenant_id: str = "global") -> None:
    """Record agent run duration."""
    agent_run_duration_seconds.labels(status=status, tenant_id=tenant_id).observe(duration_seconds)


def record_run_failure(failure_type: str, tenant_id: str = "global") -> None:
    """Record agent run failure."""
    agent_run_failures_total.labels(failure_type=failure_type, tenant_id=tenant_id).inc()


def record_run_success(tenant_id: str = "global") -> None:
    """Record successful agent run."""
    agent_run_success_total.labels(tenant_id=tenant_id).inc()


def record_todo_count(count: int, tenant_id: str = "global") -> None:
    """Record number of TODOs generated."""
    agent_todos_count.labels(tenant_id=tenant_id).observe(count)


def record_todo_duration(duration_seconds: float, status: str, tenant_id: str = "global") -> None:
    """Record TODO execution duration."""
    agent_todo_duration_seconds.labels(status=status, tenant_id=tenant_id).observe(duration_seconds)


def record_step_duration(duration_seconds: float, action: str, status: str, tenant_id: str = "global") -> None:
    """Record step execution duration."""
    agent_step_duration_seconds.labels(action=action, status=status, tenant_id=tenant_id).observe(duration_seconds)


def record_llm_call(duration_seconds: float, model: str, status: str, tenant_id: str = "global") -> None:
    """Record LLM call metrics."""
    agent_llm_calls_total.labels(model=model, status=status, tenant_id=tenant_id).inc()
    agent_llm_duration_seconds.labels(model=model, tenant_id=tenant_id).observe(duration_seconds)


def record_warmup(duration_seconds: float, model: str, provider: str, success: bool) -> None:
    """Record model warmup metrics."""
    model_warmup_duration_seconds.labels(model=model, provider=provider).observe(duration_seconds)
    if success:
        model_warmup_success_total.labels(model=model, provider=provider).inc()
    else:
        model_warmup_failure_total.labels(model=model, provider=provider).inc()


def inc_queued(tenant_id: str = "global") -> None:
    """Increment queued runs counter."""
    agent_run_queued_total.labels(tenant_id=tenant_id).inc()


def dec_queued(tenant_id: str = "global") -> None:
    """Decrement queued runs counter."""
    agent_run_queued_total.labels(tenant_id=tenant_id).dec()


def inc_running(tenant_id: str = "global") -> None:
    """Increment running runs counter."""
    agent_run_running_total.labels(tenant_id=tenant_id).inc()


def dec_running(tenant_id: str = "global") -> None:
    """Decrement running runs counter."""
    agent_run_running_total.labels(tenant_id=tenant_id).dec()
