"""
Tests for LLM fallback orchestrator with circuit breaker and cost tracking.

Validates provider fallback, circuit breaker behavior, cost caps, and health probes.
"""

import asyncio
import time

import pytest

from src.resilience.llm_fallback import (
    CircuitBreaker,
    CircuitState,
    CostTracker,
    DeterministicStubProvider,
    LLMFallbackOrchestrator,
    ProviderConfig,
)


class TestCircuitBreaker:
    """Test circuit breaker behavior."""

    def test_initial_state_closed(self):
        """Circuit starts in closed state."""
        cb = CircuitBreaker("test-provider")
        assert cb.state == CircuitState.CLOSED
        assert cb.can_attempt() is True

    def test_opens_after_threshold_failures(self):
        """Circuit opens after failure threshold."""
        cb = CircuitBreaker("test-provider", failure_threshold=3)

        # Record failures
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.can_attempt() is False

    def test_half_open_after_recovery_timeout(self):
        """Circuit moves to half-open after recovery timeout."""
        cb = CircuitBreaker(
            "test-provider",
            failure_threshold=2,
            recovery_timeout=1,  # 1 second
        )

        # Open the circuit
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # Wait for recovery timeout
        time.sleep(1.1)

        # Should transition to half-open
        assert cb.can_attempt() is True
        # Calling can_attempt should have transitioned state
        assert cb.state == CircuitState.HALF_OPEN

    def test_closes_after_success_threshold(self):
        """Circuit closes after success threshold in half-open."""
        cb = CircuitBreaker(
            "test-provider",
            failure_threshold=2,
            recovery_timeout=1,
            success_threshold=2,
        )

        # Open circuit
        cb.record_failure()
        cb.record_failure()
        time.sleep(1.1)
        cb.can_attempt()  # Transition to half-open

        # Record successes
        cb.record_success()
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_reopens_on_half_open_failure(self):
        """Circuit reopens if failure occurs in half-open."""
        cb = CircuitBreaker(
            "test-provider",
            failure_threshold=2,
            recovery_timeout=1,
        )

        # Open circuit
        cb.record_failure()
        cb.record_failure()
        time.sleep(1.1)
        cb.can_attempt()  # Half-open

        # Fail during half-open
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_success_resets_failure_count(self):
        """Success in closed state resets failure count."""
        cb = CircuitBreaker("test-provider", failure_threshold=3)

        cb.record_failure()
        assert cb.failure_count == 1
        cb.record_success()
        assert cb.failure_count == 0
        assert cb.state == CircuitState.CLOSED


class TestCostTracker:
    """Test cost tracking and caps."""

    def test_records_usage(self):
        """Cost tracker records token usage."""
        tracker = CostTracker(max_cost_per_hour=10.0)

        cost = tracker.record_usage("openai-gpt4", input_tokens=1000, output_tokens=500)
        assert cost > 0
        assert tracker.get_current_cost() == cost

    def test_enforces_cost_cap(self):
        """Cost tracker enforces hourly cost cap."""
        tracker = CostTracker(max_cost_per_hour=0.1)  # Very low cap

        # First request should be affordable
        assert tracker.can_afford(1000, "openai-gpt4") is True

        # Use up budget
        tracker.record_usage("openai-gpt4", input_tokens=1000, output_tokens=1000)

        # Next request should exceed cap
        assert tracker.can_afford(1000, "openai-gpt4") is False

    def test_cleanup_old_costs(self):
        """Cost tracker removes old entries."""
        tracker = CostTracker(max_cost_per_hour=10.0, window_size_seconds=1)

        tracker.record_usage("openai-gpt4", input_tokens=1000, output_tokens=500)
        initial_cost = tracker.get_current_cost()
        assert initial_cost > 0

        # Wait for window to expire
        time.sleep(1.1)

        # Old cost should be cleaned up
        current_cost = tracker.get_current_cost()
        assert current_cost == 0

    def test_stub_provider_is_free(self):
        """Stub provider has zero cost."""
        tracker = CostTracker(max_cost_per_hour=10.0)

        cost = tracker.record_usage("stub", input_tokens=1000, output_tokens=1000)
        assert cost == 0.0

    def test_get_stats(self):
        """Cost tracker returns statistics."""
        tracker = CostTracker(max_cost_per_hour=10.0)

        tracker.record_usage("openai-gpt4", input_tokens=1000, output_tokens=500)
        tracker.record_usage("openai-gpt4", input_tokens=500, output_tokens=250)

        stats = tracker.get_stats()
        assert stats["current_cost"] > 0
        assert stats["max_cost_per_hour"] == 10.0
        assert stats["total_input_tokens"] == 1500
        assert stats["total_output_tokens"] == 750
        assert stats["request_count"] == 2


class TestDeterministicStubProvider:
    """Test deterministic stub provider."""

    @pytest.mark.asyncio
    async def test_returns_deterministic_response(self):
        """Stub returns consistent response."""
        stub = DeterministicStubProvider("test-stub")

        result = await stub.call("Test prompt", max_tokens=100, temperature=0.7)

        assert "content" in result
        assert "Stub response" in result["content"]
        assert result["input_tokens"] > 0
        assert result["output_tokens"] > 0
        assert result["model"] == "test-stub"

    @pytest.mark.asyncio
    async def test_simulates_failures(self):
        """Stub can simulate failures."""
        stub = DeterministicStubProvider("test-stub", fail_next=2)

        # First two calls should fail
        with pytest.raises(Exception, match="simulated failure"):
            await stub.call("Test", max_tokens=100, temperature=0.7)

        with pytest.raises(Exception, match="simulated failure"):
            await stub.call("Test", max_tokens=100, temperature=0.7)

        # Third call should succeed
        result = await stub.call("Test", max_tokens=100, temperature=0.7)
        assert result["content"] is not None

    @pytest.mark.asyncio
    async def test_health_check(self):
        """Stub health check works."""
        stub = DeterministicStubProvider("test-stub")

        assert await stub.health_check() is True

        stub.set_health(False)
        assert await stub.health_check() is False


class TestLLMFallbackOrchestrator:
    """Test LLM fallback orchestrator."""

    def setup_orchestrator(self):
        """Create orchestrator with multiple providers."""
        providers = {
            "primary": DeterministicStubProvider("primary"),
            "secondary": DeterministicStubProvider("secondary"),
            "tertiary": DeterministicStubProvider("tertiary"),
        }

        configs = [
            ProviderConfig(
                name="primary",
                priority=1,
                max_cost_per_hour=10.0,
                failure_threshold=3,
            ),
            ProviderConfig(
                name="secondary",
                priority=2,
                max_cost_per_hour=5.0,
                failure_threshold=3,
            ),
            ProviderConfig(
                name="tertiary",
                priority=3,
                max_cost_per_hour=5.0,
                failure_threshold=3,
            ),
        ]

        return LLMFallbackOrchestrator(providers, configs), providers

    @pytest.mark.asyncio
    async def test_uses_primary_when_healthy(self):
        """Orchestrator uses primary provider when healthy."""
        orchestrator, providers = self.setup_orchestrator()

        result = await orchestrator.call("Test prompt", max_tokens=100)

        assert result["provider"] == "primary"
        assert result["fallback_used"] is False
        assert orchestrator.stats["successful_calls"] == 1
        assert orchestrator.stats["fallback_calls"] == 0

    @pytest.mark.asyncio
    async def test_falls_back_on_primary_failure(self):
        """Orchestrator falls back to secondary on primary failure."""
        orchestrator, providers = self.setup_orchestrator()

        # Make primary fail
        providers["primary"].fail_next = 1

        result = await orchestrator.call("Test prompt", max_tokens=100)

        assert result["provider"] == "secondary"
        assert result["fallback_used"] is True
        assert orchestrator.stats["successful_calls"] == 1
        assert orchestrator.stats["fallback_calls"] == 1

    @pytest.mark.asyncio
    async def test_cascades_through_all_providers(self):
        """Orchestrator tries all providers in order."""
        orchestrator, providers = self.setup_orchestrator()

        # Make primary and secondary fail
        providers["primary"].fail_next = 1
        providers["secondary"].fail_next = 1

        result = await orchestrator.call("Test prompt", max_tokens=100)

        assert result["provider"] == "tertiary"
        assert result["fallback_used"] is True

    @pytest.mark.asyncio
    async def test_fails_when_all_providers_fail(self):
        """Orchestrator raises exception when all providers fail."""
        orchestrator, providers = self.setup_orchestrator()

        # Make all providers fail
        providers["primary"].fail_next = 1
        providers["secondary"].fail_next = 1
        providers["tertiary"].fail_next = 1

        with pytest.raises(Exception, match="All LLM providers failed"):
            await orchestrator.call("Test prompt", max_tokens=100)

        assert orchestrator.stats["failed_calls"] == 1

    @pytest.mark.asyncio
    async def test_circuit_breaker_blocks_failed_provider(self):
        """Circuit breaker blocks provider after failures."""
        orchestrator, providers = self.setup_orchestrator()

        # Trigger circuit breaker for primary (3 failures)
        providers["primary"].fail_next = 3

        for _ in range(3):
            try:
                await orchestrator.call("Test", max_tokens=100)
            except Exception:
                pass

        # Circuit should be open now
        cb = orchestrator.circuit_breakers["primary"]
        assert cb.state == CircuitState.OPEN

        # Next call should skip primary and use secondary
        result = await orchestrator.call("Test", max_tokens=100)
        assert result["provider"] == "secondary"
        assert orchestrator.stats["circuit_breaker_blocks"] > 0

    @pytest.mark.asyncio
    async def test_cost_cap_skips_expensive_provider(self):
        """Cost cap prevents using over-budget provider."""
        providers = {
            "cheap": DeterministicStubProvider("stub"),  # Free
            "expensive": DeterministicStubProvider("openai-gpt4"),
        }

        configs = [
            ProviderConfig(
                name="expensive",
                priority=1,
                max_cost_per_hour=0.001,  # Very low cap
            ),
            ProviderConfig(
                name="cheap",
                priority=2,
                max_cost_per_hour=100.0,
            ),
        ]

        orchestrator = LLMFallbackOrchestrator(providers, configs)

        # Use up expensive provider budget
        orchestrator.cost_trackers["expensive"].record_usage("openai-gpt4", 10000, 5000)

        # Should fallback to cheap provider
        result = await orchestrator.call("Test", max_tokens=100)
        assert result["provider"] == "cheap"
        assert orchestrator.stats["cost_limited_calls"] > 0

    @pytest.mark.asyncio
    async def test_health_probe_all(self):
        """Health probe checks all providers."""
        orchestrator, providers = self.setup_orchestrator()

        health = await orchestrator.health_probe_all()

        assert health["primary"] is True
        assert health["secondary"] is True
        assert health["tertiary"] is True

        # Make one unhealthy
        providers["secondary"].set_health(False)

        health = await orchestrator.health_probe_all()
        assert health["primary"] is True
        assert health["secondary"] is False
        assert health["tertiary"] is True

    @pytest.mark.asyncio
    async def test_get_status_returns_comprehensive_info(self):
        """Status includes stats, circuit breakers, and costs."""
        orchestrator, providers = self.setup_orchestrator()

        await orchestrator.call("Test", max_tokens=100)

        status = orchestrator.get_status()

        assert "stats" in status
        assert "circuit_breakers" in status
        assert "cost_trackers" in status
        assert "health_status" in status
        assert "provider_order" in status

        assert status["stats"]["total_calls"] == 1
        assert len(status["circuit_breakers"]) == 3
        assert len(status["cost_trackers"]) == 3

    @pytest.mark.asyncio
    async def test_respects_max_tokens_per_request(self):
        """Provider with insufficient token limit is skipped."""
        providers = {
            "small": DeterministicStubProvider("small"),
            "large": DeterministicStubProvider("large"),
        }

        configs = [
            ProviderConfig(
                name="small",
                priority=1,
                max_cost_per_hour=10.0,
                max_tokens_per_request=100,  # Too small
            ),
            ProviderConfig(
                name="large",
                priority=2,
                max_cost_per_hour=10.0,
                max_tokens_per_request=10000,
            ),
        ]

        orchestrator = LLMFallbackOrchestrator(providers, configs)

        # Request more tokens than small provider supports
        result = await orchestrator.call("Test", max_tokens=5000)

        # Should use large provider
        assert result["provider"] == "large"

    @pytest.mark.asyncio
    async def test_disabled_provider_is_skipped(self):
        """Disabled provider is not attempted."""
        orchestrator, providers = self.setup_orchestrator()

        # Disable primary
        orchestrator.configs["primary"].enabled = False

        result = await orchestrator.call("Test", max_tokens=100)

        # Should skip to secondary
        assert result["provider"] == "secondary"

    @pytest.mark.asyncio
    async def test_simulated_outage_with_recovery(self):
        """Simulated provider outage still completes via fallback."""
        orchestrator, providers = self.setup_orchestrator()

        # Simulate outage: primary fails next 5 calls
        providers["primary"].fail_next = 5

        # All calls should succeed via fallback
        for i in range(5):
            result = await orchestrator.call(f"Request {i}", max_tokens=100)
            # Should use secondary since primary is failing
            assert result["provider"] in ["secondary", "tertiary"]
            assert result["fallback_used"] is True

        # Verify primary circuit is open
        assert orchestrator.circuit_breakers["primary"].state == CircuitState.OPEN

        # After recovery timeout, circuit should half-open and eventually close
        # This is tested in circuit breaker tests


class TestAcceptanceCriteria:
    """Test P4 acceptance criteria."""

    @pytest.mark.asyncio
    async def test_simulated_outage_completes_via_fallback(self):
        """
        ACCEPTANCE: Simulated provider outage still completes "ask" path via fallback.

        Scenario: Primary LLM provider goes down, system automatically falls back
        to secondary provider without user-visible errors.
        """
        # Setup 3-tier fallback
        providers = {
            "openai-primary": DeterministicStubProvider("openai-gpt4"),
            "anthropic-backup": DeterministicStubProvider("anthropic-claude"),
            "azure-emergency": DeterministicStubProvider("azure-openai"),
        }

        configs = [
            ProviderConfig(name="openai-primary", priority=1, max_cost_per_hour=10.0),
            ProviderConfig(name="anthropic-backup", priority=2, max_cost_per_hour=5.0),
            ProviderConfig(name="azure-emergency", priority=3, max_cost_per_hour=5.0),
        ]

        orchestrator = LLMFallbackOrchestrator(providers, configs)

        # === SIMULATE OUTAGE ===
        # OpenAI primary goes down (fails next 10 calls)
        providers["openai-primary"].fail_next = 10

        # === USER ASKS QUESTION ===
        # Despite outage, request succeeds via fallback
        result = await orchestrator.call(
            prompt="What is the capital of France?",
            max_tokens=100,
        )

        # === VERIFY SUCCESS ===
        assert "content" in result
        assert result["provider"] in ["anthropic-backup", "azure-emergency"]
        assert result["fallback_used"] is True

        # User gets answer despite primary being down
        assert "Stub response" in result["content"]

        # System tracked the fallback
        assert orchestrator.stats["successful_calls"] == 1
        assert orchestrator.stats["fallback_calls"] == 1
        assert orchestrator.stats["failed_calls"] == 0

        # Multiple subsequent requests also succeed
        for i in range(5):
            result = await orchestrator.call(f"Question {i}", max_tokens=100)
            assert result["provider"] != "openai-primary"  # Still down
            assert "content" in result  # Still getting responses

        # All requests succeeded via fallback
        assert orchestrator.stats["successful_calls"] == 6
        assert orchestrator.stats["failed_calls"] == 0

        print("✅ ACCEPTANCE CRITERIA MET: Provider outage handled via fallback")
