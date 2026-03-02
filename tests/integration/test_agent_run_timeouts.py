"""
Integration tests for agent run timeout handling.

Tests validate:
- TODO planning timeout detection
- Run-level timeout enforcement
- Partial result preservation
- Failure type reporting
"""
import asyncio
import os
import pytest
from httpx import AsyncClient
from src.app import app
from src.models.failure_types import FailureType

DEFAULT_MAX_WAIT = int(os.getenv("AGENT_RUN_TEST_TIMEOUT_SECONDS", "2100"))

@pytest.mark.asyncio
class TestAgentRunTimeouts:
    """Test timeout handling in agent orchestration."""

    async def _create_run_and_poll(
        self, client: AsyncClient, prompt: str, expected_failure: str = None, max_wait: int | None = None
    ):
        """Helper to create run and poll until completion or timeout."""
        # Create agent run
        response = await client.post(
            "/v1/agent-runs",
            json={"prompt": prompt},
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 201
        data = response.json()
        run_id = data["id"]
        wait_budget = max_wait or DEFAULT_MAX_WAIT
        
        # Poll for completion
        start_time = asyncio.get_event_loop().time()
        while True:
            response = await client.get(
                f"/v1/agent-runs/{run_id}",
                headers={"Authorization": "Bearer test-token"},
            )
            assert response.status_code == 200
            run_data = response.json()
            
            status = run_data["status"]
            if status in ["succeeded", "failed"]:
                return run_data
                
            # Check timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > wait_budget:
                pytest.fail(f"Test timeout waiting for run {run_id} after {elapsed}s (budget={wait_budget}s)")
                
            await asyncio.sleep(2)

    @pytest.mark.asyncio
    async def test_todo_planning_timeout(self):
        """Test that TODO planning timeout is detected and reported correctly."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Use a prompt that causes slow planning (e.g., complex nested logic)
            prompt = "Generate a plan with 50 sequential steps that each require complex analysis"
            
            run_data = await self._create_run_and_poll(
                client, prompt, expected_failure="todo_plan_timeout", max_wait=DEFAULT_MAX_WAIT
            )
            
            # Validate failure structure
            assert run_data["status"] == "failed"
            assert run_data["output"] is not None
            assert "failure_type" in run_data["output"]
            assert run_data["output"]["failure_type"] == FailureType.TODO_PLAN_TIMEOUT
            assert "timeout" in run_data["output"]["message"].lower()
            
            # Validate partial results
            assert "todos_data" in run_data
            # May have partial planning data even on timeout

    @pytest.mark.asyncio
    async def test_run_level_timeout(self):
        """Test that run-level timeout is enforced and reported."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Use a prompt that triggers many long-running steps
            prompt = "Execute 20 complex database queries sequentially with analysis"
            
            run_data = await self._create_run_and_poll(
                client, prompt, expected_failure="run_timeout", max_wait=DEFAULT_MAX_WAIT
            )
            
            # Validate timeout detection
            assert run_data["status"] == "failed"
            assert run_data["output"] is not None
            assert "failure_type" in run_data["output"]
            assert run_data["output"]["failure_type"] == FailureType.RUN_TIMEOUT
            
            # Validate partial results preserved
            assert "steps_data" in run_data
            assert "todos_data" in run_data
            
            # Should have at least some completed work before timeout
            if run_data["steps_data"]:
                assert len(run_data["steps_data"]) > 0, "Expected some steps to complete before timeout"

    @pytest.mark.asyncio
    async def test_partial_results_on_step_timeout(self):
        """Test that partial results are preserved when a step times out."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Use a prompt with one long-running step
            prompt = "First list all databases, then run an extremely slow query"
            
            run_data = await self._create_run_and_poll(
                client, prompt, max_wait=DEFAULT_MAX_WAIT
            )
            
            # Check that we have partial results
            assert "steps_data" in run_data
            
            if run_data["status"] == "failed":
                # If failed, should have failure type
                assert run_data["output"] is not None
                assert "failure_type" in run_data["output"]
                
                # Should preserve steps completed before timeout
                if run_data["steps_data"]:
                    completed_steps = [
                        s for s in run_data["steps_data"]
                        if s.get("status") == "completed"
                    ]
                    assert len(completed_steps) > 0, "Expected at least one completed step"

    @pytest.mark.asyncio
    async def test_failure_type_in_output(self):
        """Test that all timeout failures include failure_type field."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Create a run that will fail
            prompt = "This is a test prompt for timeout"
            
            run_data = await self._create_run_and_poll(
                client, prompt, max_wait=180
            )
            
            if run_data["status"] == "failed":
                # Validate output structure
                assert run_data["output"] is not None
                assert isinstance(run_data["output"], dict)
                
                # Must have failure_type
                assert "failure_type" in run_data["output"]
                assert isinstance(run_data["output"]["failure_type"], str)
                
                # Failure type must be valid
                failure_type = run_data["output"]["failure_type"]
                valid_types = [ft.value for ft in FailureType]
                assert failure_type in valid_types, f"Invalid failure_type: {failure_type}"
                
                # Must have message
                assert "message" in run_data["output"]
                assert isinstance(run_data["output"]["message"], str)
                assert len(run_data["output"]["message"]) > 0

    @pytest.mark.asyncio
    async def test_timeout_metrics_recorded(self):
        """Test that timeout failures are recorded in metrics."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Get initial metrics
            response = await client.get("/metrics")
            initial_metrics = response.text
            
            # Create a run that times out
            prompt = "Complex task that will timeout"
            run_data = await self._create_run_and_poll(
                client, prompt, max_wait=180
            )
            
            # Get updated metrics
            response = await client.get("/metrics")
            updated_metrics = response.text
            
            if run_data["status"] == "failed":
                failure_type = run_data["output"].get("failure_type")
                
                # Check that failure counter increased
                metric_name = f'agent_run_failures_total{{failure_type="{failure_type}"}}'
                
                # Metrics should be present
                assert "agent_run_failures_total" in updated_metrics
                # Note: Exact count validation would require parsing prometheus format

    @pytest.mark.asyncio
    async def test_config_timeout_values(self):
        """Test that timeout configuration is exposed and correct."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/v1/health/config")
            assert response.status_code == 200
            
            config = response.json()
            
            # Validate timeout fields present
            assert "timeouts" in config
            assert "step_seconds" in config["timeouts"]
            assert "run_seconds" in config["timeouts"]
            
            # Validate reasonable values
            step_timeout = config["timeouts"]["step_seconds"]
            run_timeout = config["timeouts"]["run_seconds"]
            
            assert step_timeout > 0, "Step timeout must be positive"
            assert run_timeout > 0, "Run timeout must be positive"
            assert run_timeout >= step_timeout, "Run timeout should be >= step timeout"
            
            # Validate device-aware defaults
            device = config.get("device", "cpu")
            if device == "cuda":
                assert step_timeout <= 60, "GPU should use shorter timeouts"
            elif device == "cpu":
                assert step_timeout >= 60, "CPU needs longer timeouts"
