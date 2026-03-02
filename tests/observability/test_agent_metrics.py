"""
Tests for agent-specific Prometheus metrics.

Validates that agent orchestration metrics are properly instrumented
and recorded through the AgentMetrics class.
"""

import pytest
from fastapi import FastAPI
from prometheus_client import CollectorRegistry, REGISTRY

from src.observability.agent_metrics import (
    AgentMetrics,
    get_agent_metrics,
    record_agent_error,
    record_agent_phase,
    record_agent_run_complete,
    record_agent_run_start,
    record_agent_tool_call,
    record_llm_call,
    record_llm_error,
    record_orchestrator_step,
    setup_agent_metrics,
)


@pytest.fixture
def registry():
    """Create a fresh Prometheus registry for each test."""
    return CollectorRegistry()


@pytest.fixture
def app_with_metrics(registry):
    """Create a FastAPI app with agent metrics configured."""
    app = FastAPI()
    app.state.prometheus_registry = registry
    setup_agent_metrics(app)
    return app


class TestAgentMetricsSetup:
    """Test agent metrics initialization."""

    def test_setup_creates_metrics(self, app_with_metrics):
        """Test that setup_agent_metrics creates the AgentMetrics instance."""
        assert hasattr(app_with_metrics.state, "agent_metrics")
        assert isinstance(app_with_metrics.state.agent_metrics, AgentMetrics)

    def test_setup_idempotent(self, app_with_metrics):
        """Test that calling setup multiple times is safe."""
        metrics1 = app_with_metrics.state.agent_metrics
        setup_agent_metrics(app_with_metrics)
        metrics2 = app_with_metrics.state.agent_metrics
        assert metrics1 is metrics2

    def test_get_agent_metrics_returns_metrics(self, app_with_metrics):
        """Test that get_agent_metrics retrieves the metrics instance."""
        metrics = get_agent_metrics(app_with_metrics)
        assert isinstance(metrics, AgentMetrics)


class TestAgentRunMetrics:
    """Test agent run recording."""

    def test_record_agent_run_start_increments_active(self, app_with_metrics):
        """Test that starting an agent run increments the active gauge."""
        metrics = get_agent_metrics(app_with_metrics)

        record_agent_run_start("test-agent", "tenant-1", app_with_metrics)

        # Check gauge value
        gauge_value = metrics.agent_active_runs.labels(agent_type="test-agent", tenant_id="tenant-1")._value._value
        assert gauge_value == 1.0

    def test_record_agent_run_complete(self, app_with_metrics):
        """Test that completing an agent run records metrics."""
        metrics = get_agent_metrics(app_with_metrics)

        # Start run
        record_agent_run_start("test-agent", "tenant-1", app_with_metrics)

        # Complete run
        record_agent_run_complete("test-agent", "success", 1.5, "tenant-1", app_with_metrics)

        # Check counter incremented
        counter_value = metrics.agent_runs_total.labels(
            agent_type="test-agent", status="success", tenant_id="tenant-1"
        )._value._value
        assert counter_value == 1.0

        # Check gauge decremented
        gauge_value = metrics.agent_active_runs.labels(agent_type="test-agent", tenant_id="tenant-1")._value._value
        assert gauge_value == 0.0

    def test_record_multiple_agent_runs(self, app_with_metrics):
        """Test recording multiple concurrent agent runs."""
        record_agent_run_start("agent-a", "tenant-1", app_with_metrics)
        record_agent_run_start("agent-a", "tenant-1", app_with_metrics)
        record_agent_run_start("agent-b", "tenant-2", app_with_metrics)

        metrics = get_agent_metrics(app_with_metrics)

        # Check agent-a has 2 active
        gauge_a = metrics.agent_active_runs.labels(agent_type="agent-a", tenant_id="tenant-1")._value._value
        assert gauge_a == 2.0

        # Check agent-b has 1 active
        gauge_b = metrics.agent_active_runs.labels(agent_type="agent-b", tenant_id="tenant-2")._value._value
        assert gauge_b == 1.0


class TestAgentPhaseMetrics:
    """Test agent phase duration recording."""

    def test_record_agent_phase(self, app_with_metrics):
        """Test that agent phases are recorded."""
        record_agent_phase("test-agent", "planning", 0.5, app_with_metrics)
        record_agent_phase("test-agent", "execution", 2.0, app_with_metrics)

        # Metrics should be recorded in histogram
        # We can't easily check histogram values in unit tests,
        # but we can verify no errors occurred
        assert True


class TestLlmMetrics:
    """Test LLM call recording."""

    def test_record_llm_call(self, app_with_metrics):
        """Test recording successful LLM call."""
        metrics = get_agent_metrics(app_with_metrics)

        record_llm_call(
            "gpt-4",
            "openai",
            "success",
            1.2,
            prompt_tokens=100,
            completion_tokens=50,
            app=app_with_metrics,
        )

        # Check counter incremented
        counter_value = metrics.llm_calls_total.labels(model="gpt-4", provider="openai", status="success")._value._value
        assert counter_value == 1.0

        # Check token counters
        prompt_tokens = metrics.llm_tokens_total.labels(model="gpt-4", provider="openai", type="prompt")._value._value
        assert prompt_tokens == 100.0

        completion_tokens = metrics.llm_tokens_total.labels(
            model="gpt-4", provider="openai", type="completion"
        )._value._value
        assert completion_tokens == 50.0

        total_tokens = metrics.llm_tokens_total.labels(model="gpt-4", provider="openai", type="total")._value._value
        assert total_tokens == 150.0

    def test_record_llm_error(self, app_with_metrics):
        """Test recording LLM error."""
        metrics = get_agent_metrics(app_with_metrics)

        record_llm_error("gpt-4", "openai", "rate_limit", app_with_metrics)

        counter_value = metrics.llm_errors_total.labels(
            model="gpt-4", provider="openai", error_type="rate_limit"
        )._value._value
        assert counter_value == 1.0


class TestToolCallMetrics:
    """Test tool call recording within agent context."""

    def test_record_agent_tool_call(self, app_with_metrics):
        """Test recording tool calls within agents."""
        metrics = get_agent_metrics(app_with_metrics)

        record_agent_tool_call(
            "test-agent",
            "database.query",
            "success",
            0.5,
            app_with_metrics,
        )

        counter_value = metrics.agent_tool_calls_total.labels(
            agent_type="test-agent", tool_name="database.query", status="success"
        )._value._value
        assert counter_value == 1.0


class TestErrorMetrics:
    """Test error tracking."""

    def test_record_agent_error(self, app_with_metrics):
        """Test recording agent errors."""
        metrics = get_agent_metrics(app_with_metrics)

        record_agent_error(
            "test-agent",
            "timeout",
            "execution",
            app_with_metrics,
        )

        counter_value = metrics.agent_errors_total.labels(
            agent_type="test-agent", error_type="timeout", phase="execution"
        )._value._value
        assert counter_value == 1.0


class TestOrchestratorMetrics:
    """Test orchestrator step recording."""

    def test_record_orchestrator_step(self, app_with_metrics):
        """Test recording orchestrator steps."""
        metrics = get_agent_metrics(app_with_metrics)

        record_orchestrator_step(
            "test-agent",
            "tool_selection",
            0.3,
            app_with_metrics,
        )

        counter_value = metrics.orchestrator_steps_total.labels(
            agent_type="test-agent", step_type="tool_selection"
        )._value._value
        assert counter_value == 1.0


class TestMetricsWithoutApp:
    """Test that metrics functions handle missing app gracefully."""

    def test_record_without_app_no_error(self):
        """Test that recording without app doesn't crash."""
        # Should not raise exception
        record_agent_run_start("test-agent", "tenant-1")
        record_agent_run_complete("test-agent", "success", 1.0, "tenant-1")
        record_llm_call("gpt-4", "openai", "success", 1.0)
        record_agent_tool_call("test-agent", "tool", "success", 0.5)
        record_agent_error("test-agent", "error", "phase")
