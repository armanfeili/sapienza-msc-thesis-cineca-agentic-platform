# Resilience Framework

The resilience package provides fault-tolerant LLM provider orchestration with automatic failover, circuit breaker patterns, cost management, and health monitoring. It ensures high availability and cost-effective operation of language model services.

## Architecture Overview

The resilience framework implements multiple layers of fault tolerance:

- **Circuit Breaker Pattern**: Prevents cascading failures by temporarily blocking failing providers
- **Automatic Failover**: Seamless fallback to backup providers when primary services fail
- **Cost Management**: Budget enforcement and usage tracking to control operational costs
- **Health Monitoring**: Continuous provider health checks with status reporting
- **Priority Ordering**: Configurable provider prioritization for optimal performance/cost balance

## Core Components

### 1. Circuit Breaker (`CircuitBreaker`)

Implements the circuit breaker pattern for individual LLM providers.

#### States
- **`CLOSED`**: Normal operation, requests flow through
- **`OPEN`**: Failure threshold exceeded, requests blocked
- **`HALF_OPEN`**: Testing recovery, limited requests allowed

#### Configuration
```python
@dataclass
class CircuitBreaker:
    provider_name: str
    failure_threshold: int = 5      # Failures before opening
    recovery_timeout: int = 60      # Seconds before testing recovery
    success_threshold: int = 2      # Successes needed to close circuit
```

#### Usage
```python
circuit = CircuitBreaker("openai-gpt4")

# Record outcomes
circuit.record_success()  # Successful request
circuit.record_failure()  # Failed request

# Check if requests allowed
if circuit.can_attempt():
    # Make request
    pass
```

### 2. Cost Tracker (`CostTracker`)

Tracks provider usage costs and enforces budget limits.

#### Features
- **Per-Provider Pricing**: Configurable costs per token for different providers
- **Sliding Window**: Cost tracking over configurable time windows (default: 1 hour)
- **Budget Enforcement**: Automatic blocking when cost caps exceeded
- **Usage Statistics**: Detailed cost and token usage reporting

#### Provider Pricing
```python
PROVIDER_COSTS = {
    "openai-gpt4": {"input": 0.03, "output": 0.06},      # $0.03/1K input, $0.06/1K output
    "openai-gpt35": {"input": 0.001, "output": 0.002},   # Cheaper GPT-3.5
    "anthropic-claude": {"input": 0.008, "output": 0.024}, # Claude pricing
    "azure-openai": {"input": 0.03, "output": 0.06},     # Azure pricing
    "stub": {"input": 0.0, "output": 0.0},              # Free test stub
}
```

#### Usage
```python
tracker = CostTracker(max_cost_per_hour=10.0)

# Record usage
cost = tracker.record_usage("openai-gpt4", input_tokens=1000, output_tokens=500)

# Check budget
if tracker.can_afford(estimated_tokens=2000, provider="openai-gpt4"):
    # Within budget
    pass

# Get statistics
stats = tracker.get_stats()
print(f"Current cost: ${stats['current_cost']:.2f}")
print(f"Remaining budget: ${stats['remaining_budget']:.2f}")
```

### 3. Provider Configuration (`ProviderConfig`)

Configuration for individual LLM providers with operational parameters.

#### Configuration Options
```python
@dataclass
class ProviderConfig:
    name: str
    priority: int                    # Lower = higher priority (1 = primary)
    max_cost_per_hour: float         # USD budget cap per hour
    max_tokens_per_request: int = 4096
    timeout_seconds: float = 30.0
    enabled: bool = True

    # Circuit breaker settings
    failure_threshold: int = 5
    recovery_timeout: int = 60
    success_threshold: int = 2
```

### 4. LLM Provider Protocol (`LLMProvider`)

Abstract interface for LLM provider implementations.

#### Protocol Definition
```python
class LLMProvider(Protocol):
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
```

### 5. Fallback Orchestrator (`LLMFallbackOrchestrator`)

Main orchestrator that coordinates provider failover and resilience.

#### Features
- **Priority-Based Failover**: Tries providers in priority order
- **Circuit Breaker Integration**: Blocks failing providers automatically
- **Cost-Aware Routing**: Considers budget limits when selecting providers
- **Health Monitoring**: Tracks provider health status
- **Comprehensive Statistics**: Detailed success/failure metrics

#### Initialization
```python
# Setup providers
providers = {
    "openai-gpt4": OpenAIProvider(api_key="..."),
    "anthropic-claude": AnthropicProvider(api_key="..."),
    "azure-openai": AzureProvider(api_key="..."),
}

# Configure provider settings
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

# Create orchestrator
orchestrator = LLMFallbackOrchestrator(providers, configs)
```

#### Making Resilient Calls
```python
result = await orchestrator.call(
    prompt="Explain quantum computing",
    max_tokens=1000,
    temperature=0.7
)

print(f"Response: {result['content']}")
print(f"Provider used: {result['provider']}")
print(f"Fallback used: {result['fallback_used']}")
print(f"Tokens: {result['input_tokens']} + {result['output_tokens']}")
```

### 6. Deterministic Stub Provider (`DeterministicStubProvider`)

Test provider that returns predictable responses for testing and development.

#### Features
- **Deterministic Output**: Consistent responses based on input
- **Failure Simulation**: Configurable failure injection for testing
- **Health Control**: Manual health status setting
- **Zero Cost**: Free usage for testing scenarios

#### Usage
```python
# Create stub provider
stub = DeterministicStubProvider("test-provider")

# Normal operation
result = await stub.call("Hello", max_tokens=100, temperature=0.5)
print(result['content'])  # "Stub response to: Hello..."

# Simulate failures
stub.fail_next = 2  # Next 2 calls will fail
try:
    await stub.call("Test", max_tokens=100, temperature=0.5)
except Exception as e:
    print(f"Expected failure: {e}")

# Control health status
stub.set_health(False)
healthy = await stub.health_check()  # Returns False
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_FALLBACK_ENABLED` | `true` | Enable automatic fallback |
| `CIRCUIT_BREAKER_ENABLED` | `true` | Enable circuit breaker protection |
| `COST_TRACKING_ENABLED` | `true` | Enable cost tracking and limits |
| `HEALTH_CHECK_INTERVAL` | `30` | Seconds between health checks |

### Provider Configuration

Providers are configured with priority ordering and resource limits:

```python
configs = [
    # Primary: High-performance, higher cost
    ProviderConfig("openai-gpt4", priority=1, max_cost_per_hour=20.0),

    # Secondary: Balanced performance/cost
    ProviderConfig("anthropic-claude", priority=2, max_cost_per_hour=10.0),

    # Tertiary: Cost-effective fallback
    ProviderConfig("openai-gpt35", priority=3, max_cost_per_hour=5.0),
]
```

## Usage Examples

### Basic Fallback Setup
```python
from src.resilience.llm_fallback import LLMFallbackOrchestrator, ProviderConfig

# Setup real providers (example)
providers = {
    "openai": OpenAIProvider(api_key=os.getenv("OPENAI_API_KEY")),
    "anthropic": AnthropicProvider(api_key=os.getenv("ANTHROPIC_API_KEY")),
}

configs = [
    ProviderConfig("openai", priority=1, max_cost_per_hour=10.0),
    ProviderConfig("anthropic", priority=2, max_cost_per_hour=5.0),
]

orchestrator = LLMFallbackOrchestrator(providers, configs)

# Make resilient call
try:
    result = await orchestrator.call(
        prompt="Write a haiku about AI",
        max_tokens=500,
        temperature=0.8
    )
    print(f"Success via {result['provider']}: {result['content'][:100]}...")

except Exception as e:
    print(f"All providers failed: {e}")
```

### Circuit Breaker Monitoring
```python
# Check circuit breaker status
status = orchestrator.get_status()

for provider, breaker in status['circuit_breakers'].items():
    state = breaker['state']
    failures = breaker['failure_count']

    if state == 'open':
        print(f"⚠️  {provider}: Circuit OPEN after {failures} failures")
    elif state == 'half_open':
        print(f"🔄 {provider}: Testing recovery")
    else:
        print(f"✅ {provider}: Operating normally")
```

### Cost Management
```python
# Monitor costs
status = orchestrator.get_status()

for provider, costs in status['cost_trackers'].items():
    current = costs['current_cost']
    max_cost = costs['max_cost_per_hour']
    utilization = costs['utilization_pct']

    print(f"{provider}: ${current:.2f}/{max_cost:.2f} ({utilization:.1f}%)")

    if utilization > 90:
        print(f"⚠️  {provider} approaching budget limit")
```

### Health Monitoring
```python
# Check provider health
health_status = await orchestrator.health_probe_all()

for provider, healthy in health_status.items():
    status = "✅ Healthy" if healthy else "❌ Unhealthy"
    print(f"{provider}: {status}")
```

### Testing with Stubs
```python
from src.resilience.llm_fallback import DeterministicStubProvider

# Setup test providers
providers = {
    "primary": DeterministicStubProvider("primary"),
    "backup": DeterministicStubProvider("backup"),
}

configs = [
    ProviderConfig("primary", priority=1, max_cost_per_hour=10.0),
    ProviderConfig("backup", priority=2, max_cost_per_hour=5.0),
]

orchestrator = LLMFallbackOrchestrator(providers, configs)

# Test normal operation
result = await orchestrator.call("Test prompt")
assert result['provider'] == 'primary'
assert not result['fallback_used']

# Test fallback
providers['primary'].fail_next = 1
result = await orchestrator.call("Test prompt")
assert result['provider'] == 'backup'
assert result['fallback_used']
```

## Performance Characteristics

- **Failover Speed**: Sub-second detection and failover
- **Circuit Breaker**: Minimal overhead when closed (< 1ms check)
- **Cost Tracking**: O(1) operations with periodic cleanup
- **Health Checks**: Configurable intervals (default 30s)
- **Memory Usage**: Bounded by provider count and cost window size

## Monitoring and Observability

### Metrics
The resilience framework integrates with the observability system:

- **Circuit Breaker States**: Per-provider circuit status
- **Failover Events**: Automatic fallback usage tracking
- **Cost Metrics**: Budget utilization and spending rates
- **Health Status**: Provider availability monitoring
- **Call Statistics**: Success/failure rates and latency

### Statistics Tracking
```python
stats = orchestrator.get_status()['stats']
print(f"Total calls: {stats['total_calls']}")
print(f"Successful: {stats['successful_calls']}")
print(f"Failed: {stats['failed_calls']}")
print(f"Fallback used: {stats['fallback_calls']}")
print(f"Cost limited: {stats['cost_limited_calls']}")
print(f"Circuit blocked: {stats['circuit_breaker_blocks']}")
```

## Error Handling

### Failure Scenarios
1. **Provider Timeout**: Automatic retry with next provider
2. **Circuit Open**: Fast-fail with clear error message
3. **Cost Exceeded**: Budget-based blocking with retry-after
4. **All Providers Fail**: Comprehensive error with failure details

### Error Propagation
```python
try:
    result = await orchestrator.call(prompt, max_tokens=1000)
except Exception as e:
    # Error includes details of all attempted providers
    print(f"LLM call failed: {e}")
    # Log structured error details
    logger.error("LLM fallback exhausted", error=str(e))
```

## Integration Points

### Orchestrator Integration
```python
from src.services.orchestrator import Orchestrator
from src.resilience.llm_fallback import LLMFallbackOrchestrator

# Inject resilient LLM layer
orchestrator = Orchestrator.from_env()
orchestrator.llm_fallback = LLMFallbackOrchestrator(providers, configs)
```

### FastAPI Integration
```python
from fastapi import FastAPI, HTTPException
from src.resilience.llm_fallback import get_llm_orchestrator

app = FastAPI()

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    orchestrator = get_llm_orchestrator()

    try:
        result = await orchestrator.call(
            prompt=request.message,
            max_tokens=request.max_tokens,
            temperature=request.temperature
        )

        return {
            "response": result['content'],
            "provider": result['provider'],
            "fallback_used": result['fallback_used'],
            "tokens": result['input_tokens'] + result['output_tokens']
        }

    except Exception as e:
        raise HTTPException(503, f"LLM service unavailable: {e}")
```

## Security Considerations

- **API Key Protection**: Secure credential handling
- **Request Validation**: Input sanitization and limits
- **Audit Logging**: Comprehensive security event tracking
- **Rate Limiting**: Integration with platform rate limiting
- **Cost Controls**: Budget enforcement prevents unexpected charges

## Testing

### Unit Testing
```python
import pytest
from src.resilience.llm_fallback import DeterministicStubProvider

@pytest.fixture
def stub_providers():
    return {
        "primary": DeterministicStubProvider("primary"),
        "backup": DeterministicStubProvider("backup"),
    }

def test_fallback_on_failure(stub_providers):
    # Setup orchestrator
    orchestrator = LLMFallbackOrchestrator(stub_providers, configs)

    # Simulate primary failure
    stub_providers['primary'].fail_next = 1

    # Should fallback to backup
    result = await orchestrator.call("Test")
    assert result['provider'] == 'backup'
    assert result['fallback_used']
```

### Integration Testing
```python
def test_cost_limits():
    tracker = CostTracker(max_cost_per_hour=1.0)

    # Should allow initial request
    assert tracker.can_afford(1000, "openai-gpt4")

    # Record expensive usage
    tracker.record_usage("openai-gpt4", 10000, 10000)  # ~$1.20

    # Should block next request
    assert not tracker.can_afford(1000, "openai-gpt4")
```

## Migration and Compatibility

- **Backwards Compatible**: Can wrap existing LLM clients
- **Incremental Adoption**: Enable features independently
- **Configuration Migration**: Smooth transition from single-provider setups
- **Fallback Modes**: Graceful degradation when resilience features unavailable</content>
<parameter name="filePath">/Users/armanfeili/Arman/Sapienza Courses/4-semester/Thesis/ILP-Thesis-2025/Cineca-Agentic-Platform/docs/general/README_resilience.md