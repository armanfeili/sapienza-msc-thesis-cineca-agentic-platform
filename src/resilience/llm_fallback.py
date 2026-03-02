"""
LLM Provider Fallback System with Circuit Breaker.

Provides resilient LLM calling with automatic failover to backup providers,
circuit breaker pattern, health probes, priority ordering, and cost caps.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failures detected, blocking requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class ProviderConfig:
    """Configuration for an LLM provider."""

    name: str
    priority: int  # Lower = higher priority (1 = primary)
    max_cost_per_hour: float  # USD per hour limit
    max_tokens_per_request: int = 4096
    timeout_seconds: float = 30.0
    enabled: bool = True

    # Circuit breaker settings
    failure_threshold: int = 5  # Failures before opening circuit
    recovery_timeout: int = 60  # Seconds before trying half-open
    success_threshold: int = 2  # Successes in half-open to close


@dataclass
class CircuitBreaker:
    """Circuit breaker for a single provider."""

    provider_name: str
    failure_threshold: int = 5
    recovery_timeout: int = 60
    success_threshold: int = 2

    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float | None = None
    opened_at: float | None = None

    def record_success(self) -> None:
        """Record successful request."""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                self._close()
        elif self.state == CircuitState.CLOSED:
            self.failure_count = 0

    def record_failure(self) -> None:
        """Record failed request."""
        self.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            # Failed during recovery test - reopen
            self._open()
        elif self.state == CircuitState.CLOSED:
            self.failure_count += 1
            if self.failure_count >= self.failure_threshold:
                self._open()

    def can_attempt(self) -> bool:
        """Check if request can be attempted."""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # Check if recovery timeout elapsed
            if self.opened_at and time.time() - self.opened_at >= self.recovery_timeout:
                self._half_open()
                return True
            return False

        # HALF_OPEN - allow limited attempts
        return True

    def _open(self) -> None:
        """Open the circuit (block requests)."""
        self.state = CircuitState.OPEN
        self.opened_at = time.time()
        self.success_count = 0
        logger.warning(
            f"Circuit breaker OPENED for provider {self.provider_name} " f"after {self.failure_count} failures"
        )

    def _half_open(self) -> None:
        """Half-open the circuit (test recovery)."""
        self.state = CircuitState.HALF_OPEN
        self.success_count = 0
        logger.info(f"Circuit breaker HALF-OPEN for provider {self.provider_name}")

    def _close(self) -> None:
        """Close the circuit (normal operation)."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        logger.info(f"Circuit breaker CLOSED for provider {self.provider_name}")

    def get_state_dict(self) -> dict[str, Any]:
        """Get current state as dictionary."""
        return {
            "provider": self.provider_name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time,
            "opened_at": self.opened_at,
        }


@dataclass
class CostTracker:
    """Track provider costs and enforce caps."""

    max_cost_per_hour: float
    window_size_seconds: int = 3600  # 1 hour

    # Cost per 1K tokens (approximate, update with real pricing)
    PROVIDER_COSTS = {
        "openai-gpt4": {"input": 0.03, "output": 0.06},
        "openai-gpt35": {"input": 0.001, "output": 0.002},
        "anthropic-claude": {"input": 0.008, "output": 0.024},
        "azure-openai": {"input": 0.03, "output": 0.06},
        "stub": {"input": 0.0, "output": 0.0},  # Test stub is free
    }

    costs: list[dict[str, Any]] = field(default_factory=list)

    def record_usage(self, provider: str, input_tokens: int, output_tokens: int) -> float:
        """Record token usage and return cost."""
        pricing = self.PROVIDER_COSTS.get(provider, {"input": 0.01, "output": 0.02})  # Default pricing

        cost = (input_tokens / 1000.0 * pricing["input"]) + (output_tokens / 1000.0 * pricing["output"])

        self.costs.append(
            {
                "timestamp": time.time(),
                "provider": provider,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost": cost,
            }
        )

        # Cleanup old entries outside window
        self._cleanup_old_costs()

        return cost

    def get_current_cost(self) -> float:
        """Get total cost in current window."""
        self._cleanup_old_costs()
        return sum(c["cost"] for c in self.costs)

    def can_afford(self, estimated_tokens: int, provider: str) -> bool:
        """Check if request is within cost cap."""
        current_cost = self.get_current_cost()

        # Estimate cost for this request (assume 50/50 input/output)
        pricing = self.PROVIDER_COSTS.get(provider, {"input": 0.01, "output": 0.02})
        estimated_cost = estimated_tokens / 2000.0 * pricing["input"] + estimated_tokens / 2000.0 * pricing["output"]

        return (current_cost + estimated_cost) <= self.max_cost_per_hour

    def _cleanup_old_costs(self) -> None:
        """Remove cost entries outside window."""
        cutoff = time.time() - self.window_size_seconds
        self.costs = [c for c in self.costs if c["timestamp"] >= cutoff]

    def get_stats(self) -> dict[str, Any]:
        """Get cost statistics."""
        self._cleanup_old_costs()
        total_cost = sum(c["cost"] for c in self.costs)
        total_input_tokens = sum(c["input_tokens"] for c in self.costs)
        total_output_tokens = sum(c["output_tokens"] for c in self.costs)

        return {
            "current_cost": total_cost,
            "max_cost_per_hour": self.max_cost_per_hour,
            "remaining_budget": max(0, self.max_cost_per_hour - total_cost),
            "utilization_pct": min(100, (total_cost / self.max_cost_per_hour) * 100),
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "request_count": len(self.costs),
        }


class LLMProvider(Protocol):
    """Protocol for LLM providers."""

    async def call(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Call the LLM provider.

        Returns:
            {
                "content": str,
                "input_tokens": int,
                "output_tokens": int,
                "model": str,
            }
        """
        ...

    async def health_check(self) -> bool:
        """Check if provider is healthy."""
        ...


class DeterministicStubProvider:
    """Deterministic stub provider for testing."""

    def __init__(self, name: str = "stub", fail_next: int = 0):
        self.name = name
        self.fail_next = fail_next  # Number of next calls to fail
        self.call_count = 0
        self.health = True

    async def call(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Return deterministic response."""
        self.call_count += 1

        if self.fail_next > 0:
            self.fail_next -= 1
            raise Exception(f"Stub provider simulated failure (call {self.call_count})")

        # Return deterministic response based on prompt
        response = f"Stub response to: {prompt[:50]}..."
        len(prompt.split()) + len(response.split())

        return {
            "content": response,
            "input_tokens": len(prompt.split()),
            "output_tokens": len(response.split()),
            "model": self.name,
        }

    async def health_check(self) -> bool:
        """Return health status."""
        return self.health

    def set_health(self, healthy: bool) -> None:
        """Set health status (for testing)."""
        self.health = healthy


class LLMFallbackOrchestrator:
    """Orchestrates LLM calls with fallback, circuit breaker, and cost tracking."""

    def __init__(
        self,
        providers: dict[str, LLMProvider],
        configs: list[ProviderConfig],
    ):
        self.providers = providers
        self.configs = {c.name: c for c in sorted(configs, key=lambda x: x.priority)}

        # Circuit breakers per provider
        self.circuit_breakers = {
            name: CircuitBreaker(
                provider_name=name,
                failure_threshold=config.failure_threshold,
                recovery_timeout=config.recovery_timeout,
                success_threshold=config.success_threshold,
            )
            for name, config in self.configs.items()
        }

        # Cost trackers per provider
        self.cost_trackers = {
            name: CostTracker(max_cost_per_hour=config.max_cost_per_hour) for name, config in self.configs.items()
        }

        # Health probe results (provider -> last_healthy_time)
        self.health_status: dict[str, float | None] = {}

        # Statistics
        self.stats = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "fallback_calls": 0,
            "cost_limited_calls": 0,
            "circuit_breaker_blocks": 0,
        }

    async def call(
        self,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Call LLM with automatic fallback.

        Tries providers in priority order, with circuit breaker and cost checks.

        Returns:
            {
                "content": str,
                "provider": str,
                "input_tokens": int,
                "output_tokens": int,
                "model": str,
                "fallback_used": bool,
            }

        Raises:
            Exception: If all providers fail or are unavailable.
        """
        self.stats["total_calls"] += 1

        errors = []
        attempted_providers = []

        # Try providers in priority order
        for provider_name, config in self.configs.items():
            if not config.enabled:
                continue

            attempted_providers.append(provider_name)

            # Check circuit breaker
            circuit = self.circuit_breakers[provider_name]
            if not circuit.can_attempt():
                self.stats["circuit_breaker_blocks"] += 1
                errors.append(f"{provider_name}: Circuit breaker {circuit.state.value}")
                continue

            # Check cost cap
            cost_tracker = self.cost_trackers[provider_name]
            if not cost_tracker.can_afford(max_tokens, provider_name):
                self.stats["cost_limited_calls"] += 1
                errors.append(f"{provider_name}: Cost cap exceeded")
                continue

            # Check max tokens
            if max_tokens > config.max_tokens_per_request:
                errors.append(
                    f"{provider_name}: Requested {max_tokens} tokens exceeds limit {config.max_tokens_per_request}"
                )
                continue

            # Attempt call
            provider = self.providers.get(provider_name)
            if not provider:
                errors.append(f"{provider_name}: Provider not found")
                continue

            try:
                # Call with timeout
                result = await asyncio.wait_for(
                    provider.call(
                        prompt=prompt,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        **kwargs,
                    ),
                    timeout=config.timeout_seconds,
                )

                # Success!
                circuit.record_success()
                cost_tracker.record_usage(
                    provider_name,
                    result.get("input_tokens", 0),
                    result.get("output_tokens", 0),
                )

                self.stats["successful_calls"] += 1
                fallback_used = provider_name != next(iter(self.configs.keys()))
                if fallback_used:
                    self.stats["fallback_calls"] += 1

                logger.info(
                    f"LLM call succeeded via {provider_name} "
                    f"(fallback={fallback_used}, tokens={result.get('input_tokens', 0)}+{result.get('output_tokens', 0)})"
                )

                return {
                    **result,
                    "provider": provider_name,
                    "fallback_used": fallback_used,
                }

            except TimeoutError:
                circuit.record_failure()
                errors.append(f"{provider_name}: Timeout after {config.timeout_seconds}s")
                logger.warning(f"LLM call timeout for {provider_name}")
                continue

            except Exception as e:
                circuit.record_failure()
                errors.append(f"{provider_name}: {e!s}")
                logger.warning(f"LLM call failed for {provider_name}: {e}")
                continue

        # All providers failed
        self.stats["failed_calls"] += 1
        error_msg = f"All LLM providers failed. Attempted: {attempted_providers}. Errors: {errors}"
        logger.error(error_msg)
        raise Exception(error_msg)

    async def health_probe(self, provider_name: str) -> bool:
        """Probe provider health."""
        provider = self.providers.get(provider_name)
        if not provider:
            return False

        try:
            healthy = await asyncio.wait_for(provider.health_check(), timeout=5.0)
            if healthy:
                self.health_status[provider_name] = time.time()
            return healthy
        except Exception as e:
            logger.warning(f"Health probe failed for {provider_name}: {e}")
            return False

    async def health_probe_all(self) -> dict[str, bool]:
        """Probe all providers concurrently."""
        tasks = {name: self.health_probe(name) for name in self.configs}

        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        return {name: result if isinstance(result, bool) else False for name, result in zip(tasks.keys(), results, strict=False)}

    def get_status(self) -> dict[str, Any]:
        """Get orchestrator status."""
        return {
            "stats": self.stats.copy(),
            "circuit_breakers": {name: cb.get_state_dict() for name, cb in self.circuit_breakers.items()},
            "cost_trackers": {name: ct.get_stats() for name, ct in self.cost_trackers.items()},
            "health_status": self.health_status.copy(),
            "provider_order": [
                {
                    "name": name,
                    "priority": config.priority,
                    "enabled": config.enabled,
                }
                for name, config in self.configs.items()
            ],
        }

    def reset_stats(self) -> None:
        """Reset statistics (for testing)."""
        self.stats = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "fallback_calls": 0,
            "cost_limited_calls": 0,
            "circuit_breaker_blocks": 0,
        }


# Example usage
async def example_usage():
    """Example of using the LLM fallback orchestrator."""
    # Setup providers (in real code, these would be actual LLM clients)
    primary = DeterministicStubProvider("openai-gpt4")
    secondary = DeterministicStubProvider("anthropic-claude")
    tertiary = DeterministicStubProvider("azure-openai")

    providers = {
        "openai-gpt4": primary,
        "anthropic-claude": secondary,
        "azure-openai": tertiary,
    }

    configs = [
        ProviderConfig(
            name="openai-gpt4",
            priority=1,  # Primary
            max_cost_per_hour=10.0,
            max_tokens_per_request=8192,
        ),
        ProviderConfig(
            name="anthropic-claude",
            priority=2,  # Secondary fallback
            max_cost_per_hour=5.0,
            max_tokens_per_request=4096,
        ),
        ProviderConfig(
            name="azure-openai",
            priority=3,  # Tertiary fallback
            max_cost_per_hour=8.0,
            max_tokens_per_request=8192,
        ),
    ]

    orchestrator = LLMFallbackOrchestrator(providers, configs)

    # Normal call (uses primary)
    result = await orchestrator.call("What is the capital of France?")
    print(f"Result: {result['content']}")
    print(f"Provider: {result['provider']}")
    print(f"Fallback used: {result['fallback_used']}")

    # Simulate primary failure - should fallback to secondary
    primary.fail_next = 1
    result = await orchestrator.call("What is 2+2?")
    print(f"\nFallback result: {result['content']}")
    print(f"Provider: {result['provider']}")
    print(f"Fallback used: {result['fallback_used']}")

    # Check status
    status = orchestrator.get_status()
    print(f"\nStats: {status['stats']}")


if __name__ == "__main__":
    asyncio.run(example_usage())
